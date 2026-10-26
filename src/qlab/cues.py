from __future__ import annotations

import re
from collections import Counter

from pydantic import BaseModel, Field
from typing import Literal, NamedTuple, get_args

from qlab import QLab

# QLab cue types
QLAB_TYPES = Literal[
    'Network', 'MIDI', 'Video', 'Audio', 'Text', 'Group', 'Cue List', 'Cart', 'Fade'
]

QLAB_TYPE_NAMES = get_args(QLAB_TYPES)


def unknown_cue_types(show_cues: list) -> dict[str, int]:
    """Cue types set in ShowRunner that QLab cannot create, with their cue counts."""
    return dict(
        Counter(c.cue_type for c in show_cues if c.cue_type and c.cue_type not in QLAB_TYPE_NAMES)
    )


class TypeMapping(BaseModel):
    """How a non-QLab cue type is sent to QLab."""

    type: QLAB_TYPES
    color: str | None = None  # QLab colour name, e.g. 'orange'
    osc: str | None = None  # sent as the cue's custom string (Network cues); see render_osc
    patch: str | None = None  # QLab network patch uniqueID (Network cues); None: no patch
    prefix: str | None = None  # QLab number prefix for this type's cues, e.g. 'tm' -> 'tm42'


class MissingPatch(Exception):
    """Layers whose chosen network patch is no longer in QLab. ``layers`` lists them."""

    def __init__(self, layers: list[str]):
        super().__init__(f'network patch not found in QLab for: {", ".join(layers)}')
        self.layers = layers


class MissingPrefix(Exception):
    """Cue types whose mapping has no QLab number prefix. ``types`` lists them."""

    def __init__(self, types: list[str]):
        super().__init__(f'no QLab number prefix for: {", ".join(types)}')
        self.types = types


def patch_numbers(patches: list[dict], chosen: dict[str, str | None]) -> dict[str, int]:
    """Map each layer's chosen patch ``uniqueID`` to QLab's patch number (1-based list position).

    ``patches`` is QLab's network patch list; layers chosen as None get no number.
    Raises ``MissingPatch`` if a chosen patch is not in the list.
    """
    numbers = {p['uniqueID']: n for n, p in enumerate(patches, 1)}
    chosen = {layer: pid for layer, pid in chosen.items() if pid}
    missing = [layer for layer, pid in chosen.items() if pid not in numbers]
    if missing:
        raise MissingPatch(missing)
    return {layer: numbers[pid] for layer, pid in chosen.items()}


def render_osc(template: str, cue: QLabCue, number: str, prefix: str) -> str:
    """Fill {number} (the ShowRunner cue number), {prefix} (the QLab number prefix), {name} and
    {layer} from the cue; other {words} stay as typed."""
    values = {'number': number, 'prefix': prefix, 'name': cue.name or '', 'layer': cue.layer or ''}
    return re.sub(r'\{(\w+)\}', lambda m: values.get(m.group(1), m.group(0)), template)


NOTE_ON = 0x90

class LayerInfo(NamedTuple):
    """A ShowRunner layer as QLab sync uses it: its cue type and the QLab number prefix."""

    type: str
    prefix: str


def layer_infos(layers: list[dict]) -> dict[str, LayerInfo]:
    """Layer name -> LayerInfo, from ShowRunner's get_layers() dicts."""
    return {x['name']: LayerInfo(x['type'], x['prefix']) for x in layers}


def layer_info(layer_types: dict[str, LayerInfo], name: str | None) -> LayerInfo:
    """A layer's info. A name the show does not have is generic, prefixed with its letters."""
    return layer_types.get(name) or LayerInfo('generic', re.sub(r'[^A-Za-z]', '', name or ''))

CUE_TYPES = {
    'lights': 'Network',
    'sound': 'Network',
    'video': 'Video',
    'audio': 'Audio',
    'stage': 'Network',
}


class QLabCue(BaseModel):
    """QLab cue"""

    id: str | None = Field(None, alias='uniqueID')  # str: keep QLab's casing, UUID lowercases it
    type: QLAB_TYPES
    layer: str | None = None

    number: str | None = None
    name: str | None = None
    notes: str | None = None
    cues: list['QLabCue'] | None = None
    colorName: str | None = None
    customString: str | None = None
    armed: bool | None = None
    patch: int | None = None  # network patch number; None leaves QLab's patch as it is


class QLabCueList(QLabCue):
    number: str | None = None
    id: str | None = Field(None, alias='uniqueID')
    cues: list[QLabCue] | None = None
    colorName: str | None = None
    flagged: bool | None = None
    name: str | None = None
    listName: str | None = None
    type: str = 'Cue List'


def qlab_number(number, point, prefix: str = '') -> str:
    """QLab cue number for a ShowRunner cue: layer/type *prefix*, number, then ``.point``."""
    if number is None:
        return ''
    cue_number = str(number)
    if point:
        cue_number += f'.{point}'
    return f'{prefix}{cue_number}'


def qlab_prefix(cue, layer_types: dict[str, LayerInfo], type_overrides=None) -> str:
    """The QLab number prefix ``sync_show_cues`` gives *cue*: its type mapping's, else its layer's."""
    mapping = (type_overrides or {}).get(cue.cue_type)
    return (mapping.prefix or '') if mapping else layer_info(layer_types, cue.layer).prefix


def group_qlab_number(number: str | None, layer: str | None,
                      layer_types: dict[str, LayerInfo]) -> str:
    """QLab number for a ShowRunner group: its layer's prefix and number, as for a cue.

    '' if the group has no number or no layer (a number without a layer would be ambiguous).
    """
    if not number or not layer:
        return ''
    return qlab_number(number, 0, layer_info(layer_types, layer).prefix)


def show_qlab_number(cue, layer_types: dict[str, LayerInfo], type_overrides=None) -> str:
    """The QLab number ``sync_show_cues`` gives *cue*: the same rule, shared with group pull."""
    return qlab_number(cue.number, cue.point, qlab_prefix(cue, layer_types, type_overrides))


def group_tree(cuelists: list) -> list[dict]:
    """QLab Group cues as dicts, outer groups first.

    Each: ``uid``, ``name``, ``color`` (colorName), ``parent`` (uid of the enclosing group, else
    None), ``list`` (uid of the cue list it sits in), ``index`` (its position among its siblings),
    ``children`` (uids of every direct child, in order), ``members`` (the non-group children as
    QLabCue, in order). Cue Lists are not groups and are skipped.
    """
    groups: list[dict] = []
    by_uid: dict[str, dict] = {}

    def walk(items, parent: str | None, list_uid: str | None) -> None:
        for index, cue in enumerate(items or []):
            if parent:
                by_uid[parent]['children'].append(str(cue.id))
            if cue.type == 'Group':
                node = {
                    'uid': str(cue.id), 'name': cue.name or '', 'color': cue.colorName,
                    'number': cue.number or '', 'parent': parent, 'list': list_uid, 'index': index,
                    'children': [], 'members': [],
                }
                groups.append(node)
                by_uid[node['uid']] = node
                walk(cue.cues, node['uid'], list_uid)
            elif parent:
                by_uid[parent]['members'].append(cue)

    for cl in cuelists:
        walk(cl.cues, None, str(cl.id))
    return groups


def qlab_cues_by_uid(cuelists: list) -> dict[str, QLabCue]:
    """Every cue and group in *cuelists* by uniqueID, nested ones included."""
    found: dict[str, QLabCue] = {}
    stack = list(cuelists)
    while stack:
        cue = stack.pop()
        if cue.id:
            found[cue.id] = cue
        stack.extend(cue.cues or [])
    return found


def flatten_cuelist(cuelist: QLabCue) -> dict[str, QLabCue]:
    """Flatten a QLab cuelist into a dictionary of cues by number"""
    results = {cuelist.number: cuelist}
    for cue in cuelist.cues:
        if cue.cues:
            # print('nested cuelist', cue.cues)
            results.update(flatten_cuelist(cue))
            # print('parsing cue', cuelist)
        if not cue.number:
            continue
        results[cue.number] = cue
    return results


class QLabError(Exception):
    """QLab answered a command with a status other than ok."""


def _ok(reply: dict) -> dict:
    if reply.get('status') != 'ok':
        raise QLabError(f"{reply.get('address')}: {reply.get('status')}")
    return reply


class Cues:
    def __init__(self, q: QLab, channels: dict = {}):
        self.channels = channels
        self.q = q
        self.cuelists = self.get_cuelists()
        self.cues: dict[str, QLabCue] = {}
        for cl in self.cuelists:
            if cl.cues:
                self.cues.update(flatten_cuelist(cl))
        self.by_uid = qlab_cues_by_uid(self.cuelists)

    def get_cuelists(self):
        data = self.q.send('/cueLists')['data']
        return [QLabCueList(**cuelist) for cuelist in data]

    def sync_show_cues(
        self,
        show_cues: list,
        layer_types: dict[str, LayerInfo],
        type_overrides: dict[str, TypeMapping] | None = None,
        patches: dict[str, int] | None = None,
        type_patches: dict[str, int] | None = None,
        links: dict[int, tuple[str, str]] | None = None,
    ) -> list[QLabCue]:
        """Sync ShowRunner Cue models to QLab.

        Converts each ShowRunner Cue into a QLabCue (applying layer prefixes
        and cue-type mapping) then creates or updates the cue in QLab. A cue linked to a QLab
        uniqueID (``external_id``) updates that cue, so a renumber moves it instead of making a
        duplicate. An unlinked cue takes the QLab cue with its number, unless that one is linked.

        Args:
            show_cues: List of ShowRunner Cue model instances.
            layer_types: Maps layer name to its LayerInfo (type and prefix, from the layers table).
            type_overrides: Maps a non-QLab cue type to how it is sent to QLab.
            patches: Maps layer name to the network patch number its cues use (see patch_numbers).
            type_patches: Maps a non-QLab cue type to the network patch number its mapping chose.
                A mapped cue takes its patch from its mapping only, never from its layer.

        Returns:
            List of QLabCue objects that were synced. If *links* is given, it is filled with
            each synced ShowRunner cue id -> (QLab uniqueID, QLab number).
        """
        synced: list[QLabCue] = []
        previous = None
        claimed = {c.external_id for c in show_cues if c.external_id}
        used: set[str] = set()  # QLab cues already written by this sync
        for cue in show_cues:
            if not cue.layer or cue.number is None:  # unnumbered: nothing to send yet
                continue
            layer = layer_info(layer_types, cue.layer).type
            # A plugin's own cue type (e.g. 'TheatreMix') is not a QLab type: use its mapping,
            # else the layer's
            mapping = (type_overrides or {}).get(cue.cue_type)
            cue_type = (
                cue.cue_type
                if cue.cue_type in QLAB_TYPE_NAMES
                else mapping.type if mapping else CUE_TYPES.get(layer, 'Network')
            )
            # A mapped cue is numbered with its mapping's prefix, not its layer's
            qlab_number = show_qlab_number(cue, layer_types, type_overrides)

            # Only Network cues take a patch
            if mapping:
                patch = (type_patches or {}).get(cue.cue_type)
            else:
                patch = (patches or {}).get(cue.layer)
            q = QLabCue(
                type=cue_type,
                layer=layer,
                number=qlab_number,
                name=cue.name,
                notes=cue.notes,
                patch=patch if cue_type == 'Network' else None,
            )
            if mapping:
                q.colorName = mapping.color
                q.customString = (
                    render_osc(mapping.osc, q, cue.number, qlab_prefix(cue, layer_types, type_overrides))
                    if mapping.osc else None
                )

            linked = self.by_uid.get(cue.external_id) if cue.external_id else None
            if linked is None:
                by_number = self.cues.get(qlab_number)
                if by_number and by_number.id not in claimed:
                    linked = by_number
            if linked is not None and linked.id in used:  # a duplicate link: make a new cue
                linked = None
            if linked is not None:
                q.id = linked.id
                previous = self.update_cue(q).id
            else:
                previous = self.create_cue(q, previous).id
            used.add(str(q.id))
            if links is not None:
                links[cue.id] = (str(q.id), qlab_number)
            synced.append(q)
        return synced

    def update_cue(self, cue: QLabCue):
        """Update a cue"""
        if not cue.id:
            cue.id = self.q.get_cue_property(cue.number, 'uniqueID')
        if cue.number:
            self.q.send(f'/cue_id/{cue.id}/number', value=cue.number)
        if cue.name:
            self.q.send(f'/cue_id/{cue.id}/name', value=cue.name)
        if cue.notes:
            self.q.send(f'/cue_id/{cue.id}/notes', value=cue.notes)

        # Layer specific settings
        if cue.layer == 'lights':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'orange')
            self.q.send(f'/cue_id/{cue.id}/customString', f'/eos/cue/{cue.number}/fire')
        elif cue.layer == 'sound':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'blue')
            self.q.send(
                f'/cue_id/{cue.id}/customString', f'/jump {cue.number.replace("s", "")}'
            )
        elif cue.layer == 'audio':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'cyan')
        elif cue.layer == 'video':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'purple')
        # Per-type settings from the sync dialog win over the layer's
        if cue.colorName:
            self.q.send(f'/cue_id/{cue.id}/colorName', cue.colorName)
        if cue.customString:
            self.q.send(f'/cue_id/{cue.id}/customString', cue.customString)
        if cue.patch:
            self.q.send(f'/cue_id/{cue.id}/networkPatchNumber', cue.patch)
        return cue

    def workspace_id(self) -> str:
        return self._workspace()

    def _workspace(self) -> str:
        # Unprefixed cue commands only reach one workspace, so refuse to guess between several
        open_ = _ok(self.q.send('/workspaces'))['data']
        if len(open_) != 1:
            raise QLabError(f'expected one open workspace, found {len(open_)}')
        return open_[0]['uniqueID']

    def new_group(self, name: str, colour: str | None, number: str = '') -> str:
        """Create an empty Group cue at the end of the list; returns its uniqueID."""
        uid = _ok(self.q.send('/new', 'group'))['data']
        try:
            self.set_group(uid, name, colour, number)
        except QLabError:
            self.delete_cue(uid)  # the caller never gets this uid, so it would be left behind
            raise
        return uid

    def set_group(self, uid: str, name: str, colour: str | None, number: str = '') -> None:
        # shortcut: an empty number is not sent (the OSC builder drops '' and QLab rejects a bare
        # number write), so clearing a group's number in ShowRunner leaves the QLab number, upgrade
        # once osc.build sends empty strings and QLab accepts them as a clear
        if number:
            _ok(self.q.send(f'/cue_id/{uid}/number', value=number))
        _ok(self.q.send(f'/cue_id/{uid}/name', value=name or 'Group'))
        if colour:
            _ok(self.q.send(f'/cue_id/{uid}/colorName', colour))

    def move_cue(self, cue_uid: str, index: int, parent_uid: str) -> None:
        """Move a cue to *index* among the children of *parent_uid* (a Group or the cue list).

        Verified on QLab 5.6.3: [index, parent] works; an index alone is an error, so a cue
        leaving a group names the cue list as its parent. Lists are sent because the OSC
        builder drops a bare 0.
        """
        _ok(self.q.send(f'/workspace/{self._workspace()}/move/{cue_uid}', [index, parent_uid]))

    def delete_cue(self, cue_uid: str) -> None:
        """Delete a cue by uniqueID. Verified on 5.6.3 (delete_id); a Group's children go too."""
        _ok(self.q.send(f'/workspace/{self._workspace()}/delete_id/{cue_uid}'))

    def create_cue(self, cue: QLabCue, previous: str = None):
        """Create a cue"""
        cue_type = cue.type.lower()
        # TODO We should be able to send /new type [previous]
        # to create a new cue after the previous one, but it's not working.
        if previous:
            cue_type = [cue_type, previous]
        cue.id = self.q.send(
            '/new',
            cue_type,
        )['data']
        self.update_cue(cue)
        return cue
