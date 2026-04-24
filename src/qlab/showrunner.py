"""QLab - A ShowRunner plugin for syncing cues to QLab."""

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select

import showrunner
from showrunner.models import Cue as ShowCue
from showrunner.models import CueList
from showrunner.plugins.db import get_db

from qlab.cues import Cues

router = APIRouter(prefix="/qlab", tags=["QLab"])

_cues: Cues | None = None


def _get_cues() -> Cues:
    """Return the current Cues instance, or raise if not connected."""
    if _cues is None:
        raise HTTPException(503, 'QLab not connected — configure address/port first')
    return _cues


@router.get("/")
async def index():
    connected = _cues is not None
    return {"plugin": "QLab", "status": "connected" if connected else "disconnected"}


@router.post("/connect")
async def connect(address: str = 'localhost', port: int = 53000):
    """Connect to a QLab instance."""
    global _cues
    _cues = Cues(address=address, port=port)
    return {"status": "connected", "address": address, "port": port}


@router.post("/sync/{cue_list_id}")
async def sync_cuelist(cue_list_id: int):
    """Sync a ShowRunner cuelist to the connected QLab instance.

    Reads all cues from the given CueList and creates/updates
    them in QLab with the appropriate layer prefixes and routing.
    """
    cues = _get_cues()
    db = get_db()

    with db.session() as s:
        cue_list = s.get(CueList, cue_list_id)
        if not cue_list:
            raise HTTPException(404, f'CueList {cue_list_id} not found')
        show_cues = s.exec(
            select(ShowCue)
            .where(ShowCue.cue_list_id == cue_list_id)
            .order_by(ShowCue.sequence, ShowCue.number, ShowCue.point)
        ).all()

    if not show_cues:
        return {"synced": 0, "cues": []}

    synced = cues.sync_show_cues(show_cues)
    return {
        "synced": len(synced),
        "cues": [q.model_dump() for q in synced],
    }


@router.get("/cuelists")
async def list_qlab_cuelists():
    """List cue lists from the connected QLab instance."""
    cues = _get_cues()
    return [cl.model_dump() for cl in cues.cuelists]


class QLabPlugin:
    """A ShowRunner plugin for syncing cue lists to QLab."""

    @showrunner.hookimpl
    def showrunner_register(self):
        return {
            "name": "QLab",
            "description": "Syncs ShowRunner cue lists to QLab via OSC.",
            "version": "0.1.0",
        }

    @showrunner.hookimpl
    def showrunner_startup(self, app):
        pass

    @showrunner.hookimpl
    def showrunner_shutdown(self, app):
        global _cues
        _cues = None

    @showrunner.hookimpl
    def showrunner_get_routes(self):
        return router

    @showrunner.hookimpl
    def showrunner_get_commands(self):
        return []

    @showrunner.hookimpl
    def showrunner_get_nav(self):
        return {'label': 'QLab', 'path': '/qlab', 'icon': 'speaker', 'order': 60}

    @showrunner.hookimpl
    def showrunner_get_status(self):
        if _cues is not None:
            return {'icon': 'wifi', 'tooltip': 'QLab connected', 'color': 'green'}
        return {'icon': 'wifi_off', 'tooltip': 'QLab disconnected', 'color': 'gray'}


plugin = QLabPlugin()
