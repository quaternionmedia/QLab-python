from __future__ import annotations

import re
from collections import Counter
from uuid import UUID

from pydantic import BaseModel, Field
from typing import Literal, get_args

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


class MissingPatch(Exception):
    """Layers whose chosen network patch is no longer in QLab. ``layers`` lists them."""

    def __init__(self, layers: list[str]):
        super().__init__(f'network patch not found in QLab for: {", ".join(layers)}')
        self.layers = layers


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


def render_osc(template: str, cue: QLabCue) -> str:
    """Fill {number}, {name} and {layer} from the cue; other {words} stay as typed."""
    values = {'number': cue.number, 'name': cue.name or '', 'layer': cue.layer or ''}
    return re.sub(r'\{(\w+)\}', lambda m: values.get(m.group(1), m.group(0)), template)


NOTE_ON = 0x90

# QLab number prefix and cue type, keyed by ShowRunner layer type (layers.type)
LAYER_IDS = {'lights': '', 'sound': 's', 'video': 'v', 'audio': 'a'}
CUE_TYPES = {
    'lights': 'Network',
    'sound': 'Network',
    'video': 'Video',
    'audio': 'Audio',
    'stage': 'Network',
}


class QLabCue(BaseModel):
    """QLab cue"""

    id: UUID | None = Field(None, alias='uniqueID')
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
    id: UUID | None = Field(None, alias='uniqueID')
    cues: list[QLabCue] | None = None
    colorName: str | None = None
    flagged: bool | None = None
    name: str | None = None
    listName: str | None = None
    type: str = 'Cue List'


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


class Cues:
    def __init__(self, q: QLab, channels: dict = {}):
        self.channels = channels
        self.q = q
        self.cuelists = self.get_cuelists()
        self.cues: dict[str, QLabCue] = {}
        for cl in self.cuelists:
            if cl.cues:
                self.cues.update(flatten_cuelist(cl))

    def get_cuelists(self):
        data = self.q.send('/cueLists')['data']
        return [QLabCueList(**cuelist) for cuelist in data]

    def sync_show_cues(
        self,
        show_cues: list,
        layer_types: dict[str, str],
        type_overrides: dict[str, TypeMapping] | None = None,
        patches: dict[str, int] | None = None,
        type_patches: dict[str, int] | None = None,
    ) -> list[QLabCue]:
        """Sync ShowRunner Cue models to QLab.

        Converts each ShowRunner Cue into a QLabCue (applying layer prefixes
        and cue-type mapping) then creates or updates the cue in QLab.

        Args:
            show_cues: List of ShowRunner Cue model instances.
            layer_types: Maps layer name to ShowRunner layer type (from the layers table).
            type_overrides: Maps a non-QLab cue type to how it is sent to QLab.
            patches: Maps layer name to the network patch number its cues use (see patch_numbers).
            type_patches: Maps a non-QLab cue type to the network patch number its mapping chose.
                A mapped cue takes its patch from its mapping only, never from its layer.

        Returns:
            List of QLabCue objects that were synced.
        """
        synced: list[QLabCue] = []
        previous = None
        for cue in show_cues:
            if not cue.layer:
                continue
            layer = layer_types.get(cue.layer, 'generic')
            # A plugin's own cue type (e.g. 'TheatreMix') is not a QLab type: use its mapping,
            # else the layer's
            mapping = (type_overrides or {}).get(cue.cue_type)
            cue_type = (
                cue.cue_type
                if cue.cue_type in QLAB_TYPE_NAMES
                else mapping.type if mapping else CUE_TYPES.get(layer, 'Network')
            )
            layer_prefix = LAYER_IDS.get(layer, '')
            cue_number = str(cue.number)
            if cue.point:
                cue_number += f'.{cue.point}'
            qlab_number = f'{layer_prefix}{cue_number}'

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
                q.customString = render_osc(mapping.osc, q) if mapping.osc else None

            if qlab_number in self.cues:
                previous = self.update_cue(q).id
            else:
                previous = self.create_cue(q, previous).id
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

    def create_cue(self, cue: QLabCue, previous: UUID = None):
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
