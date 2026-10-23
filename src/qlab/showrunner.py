"""QLab - A ShowRunner plugin for syncing cues to QLab.

Connections are configured at ``/qlab`` through ShowRunner's connection interface
(``showrunner.connection``). Each out port is one QLab instance (OSC over TCP, SLIP).
Settings live per show in the DB (key ``qlab.settings``), falling back to
``[plugins.qlab]`` in show.toml::

    [[plugins.qlab.connections]]
    name = "main"
    ports = [{ name = "out", address = "192.168.1.20", port = 53000 }]
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field, model_validator
from sqlmodel import select

from showrunner.connection import (
    Connection,
    ConnectionManager,
    ConnectionPlugin,
    ConnectionSettings,
    Mapping,
    Port,
    common_routes,
)
from showrunner.connection_ui import ConnectionPage
from showrunner.layers import get_layers
from showrunner.models import Cue as ShowCue
from showrunner.models import CueList
from showrunner.plugins.db import get_db

from qlab.cues import Cues
from qlab.qlab import QLab

router = APIRouter(prefix="/qlab", tags=["QLab"])


# ---------------------------------------------------------------------------
# Settings models
# ---------------------------------------------------------------------------


class QLabPort(Port):
    address: str = Field('localhost', min_length=1)  # QLab host
    port: int = Field(53000, ge=1, le=65535)  # QLab OSC port

    @model_validator(mode='after')
    def _out_only(self):
        if self.direction == 'in':
            raise ValueError('QLab connections only have output ports')
        return self


class QLabConnection(Connection):
    ports: list[QLabPort] = Field(..., min_length=1)


class QLabSettings(ConnectionSettings):
    connections: list[QLabConnection] = Field(default_factory=list)
    mappings: list[Mapping] = Field(default_factory=list)  # unused: cue sync goes through Cues


# ---------------------------------------------------------------------------
# Manager: each open port holds a QLab client
# ---------------------------------------------------------------------------


class QLabManager(ConnectionManager):
    protocol = 'qlab'
    settings_cls = QLabSettings
    settings_key = 'qlab.settings'
    toml_section = 'qlab'

    def open(self, conn: Connection, port: QLabPort) -> QLab:
        return QLab(port.address, port.port)  # connects and sends /alwaysReply

    def close(self, key: tuple[str, str], handle: QLab) -> None:
        handle.close()

    def matches(self, mapping: Mapping, msg: dict) -> bool:
        return False  # no input ports

    def describe(self, msg: dict) -> str:
        return ''

    def client(self, connection: str | None = None) -> QLab:
        """The open QLab client for ``connection`` (default: first with an out port)."""
        name = connection or self.default_output()
        with self._lock:
            for (conn, _), handle in self.handles.items():
                if conn == name:
                    return handle
        raise KeyError(f"no open QLab connection{f' {name!r}' if name else ''}")


_qlab = QLabManager()
common_routes(router, _qlab, 'QLab', lambda: True)


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------


def _get_cues() -> Cues:
    """A Cues bound to the open QLab client; 503 if no connection is open."""
    try:
        return Cues(_qlab.client())
    except KeyError as e:
        raise HTTPException(503, f'QLab not connected: {e.args[0]}')


def sync_cue_list(cues: Cues, cue_list_id: int, layers: list[str] | None = None) -> dict:
    """Push a ShowRunner cue list to QLab, optionally only cues on the named layers.

    ``layers=None`` syncs every layer. Raises ``ValueError`` if the cue list is missing.
    """
    db = get_db()
    with db.session() as s:
        cue_list = s.get(CueList, cue_list_id)
        if not cue_list:
            raise ValueError(f'CueList {cue_list_id} not found')
        show_cues = s.exec(
            select(ShowCue)
            .where(ShowCue.cue_list_id == cue_list_id)
            .order_by(ShowCue.sequence, ShowCue.number, ShowCue.point)
        ).all()
        layer_types = {layer['name']: layer['type'] for layer in get_layers(s, cue_list.show_id)}
    if layers is not None:
        show_cues = [c for c in show_cues if c.layer in layers]
    if not show_cues:
        return {'synced': 0, 'cues': []}
    synced = cues.sync_show_cues(show_cues, layer_types)
    return {'synced': len(synced), 'cues': [q.model_dump() for q in synced]}


@router.post("/sync/{cue_list_id}")
async def sync_cuelist(cue_list_id: int, layers: list[str] | None = Query(None)):
    """Sync a ShowRunner cue list to the connected QLab instance.

    ``?layers=Lights&layers=Sound`` limits the sync to those layers; omit to sync all.
    """
    try:
        return sync_cue_list(_get_cues(), cue_list_id, layers)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/cuelists")
async def list_qlab_cuelists():
    """List cue lists from the connected QLab instance."""
    cues = _get_cues()
    return [cl.model_dump() for cl in cues.cuelists]


# ---------------------------------------------------------------------------
# /qlab page and plugin
# ---------------------------------------------------------------------------


class QLabPage(ConnectionPage):
    path = '/qlab'
    title = 'QLab'
    port_defaults = {'address': 'localhost', 'port': 53000}

    def port_fields(self, p: dict, refresh) -> None:
        from nicegui import ui

        ui.input('Address', value=p['address'],
                 on_change=lambda e: p.update(address=e.value)).classes('grow')
        ui.number('Port', value=p['port'], min=1, max=65535, precision=0,
                  on_change=lambda e: p.update(port=int(e.value or 0))).classes('w-24')

    def extra_cards(self, ui) -> None:
        show_id = self.manager.show_id
        with get_db().session() as s:
            cue_lists = {cl.id: cl.name for cl in s.exec(
                select(CueList).where(CueList.show_id == show_id)).all()} if show_id else {}
            layer_names = [layer['name'] for layer in get_layers(s, show_id)] if show_id else []
        state = {'cue_list': next(iter(cue_lists), None), 'layers': set(layer_names)}

        with ui.card().classes('w-full'):
            ui.label('Sync to QLab').classes('text-h6')
            if not cue_lists:
                ui.label('No cue lists in this show.').classes('text-grey')
                return
            with ui.row().classes('w-full items-center gap-2'):
                ui.select(cue_lists, label='Cue list', value=state['cue_list'],
                          on_change=lambda e: state.update(cue_list=e.value)).classes('w-64')
                ui.button('Sync', icon='sync', on_click=lambda: self._sync(ui, state)
                          ).props('color=primary')
            with ui.row().classes('w-full items-center gap-2'):
                ui.label('Layers:')
                for name in layer_names:
                    ui.checkbox(name, value=True, on_change=lambda e, n=name: (
                        state['layers'].add(n) if e.value else state['layers'].discard(n)))

    @staticmethod
    def _sync(ui, state: dict) -> None:
        try:
            result = sync_cue_list(_get_cues(), state['cue_list'], sorted(state['layers']))
        except Exception as e:  # HTTPException (not connected) or a QLab error
            ui.notify(str(getattr(e, 'detail', e)), type='negative', multi_line=True)
            return
        ui.notify(f"Synced {result['synced']} cue(s)", type='positive')


class QLabPlugin(ConnectionPlugin):
    """Syncs ShowRunner cue lists to QLab over OSC/TCP."""

    protocol = 'qlab'
    label = 'QLab'
    description = 'Syncs ShowRunner cue lists to QLab via OSC over TCP.'
    version = '0.2.0'
    nav_label = 'QLab'
    icon = 'speaker'
    nav_order = 60
    manager = _qlab
    router = router
    page_cls = QLabPage


plugin = QLabPlugin()
