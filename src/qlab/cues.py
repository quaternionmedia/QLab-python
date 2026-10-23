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
    ) -> list[QLabCue]:
        """Sync ShowRunner Cue models to QLab.

        Converts each ShowRunner Cue into a QLabCue (applying layer prefixes
        and cue-type mapping) then creates or updates the cue in QLab.

        Args:
            show_cues: List of ShowRunner Cue model instances.
            layer_types: Maps layer name to ShowRunner layer type (from the layers table).
            type_overrides: Maps a non-QLab cue type to how it is sent to QLab.

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

            q = QLabCue(
                type=cue_type,
                layer=layer,
                number=qlab_number,
                name=cue.name,
                notes=cue.notes,
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
            self.q.send(f'/cue_id/{cue.id}/networkPatchNumber', 1)
        elif cue.layer == 'sound':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'blue')
            self.q.send(
                f'/cue_id/{cue.id}/customString', f'/jump {cue.number.replace("s", "")}'
            )
            self.q.send(f'/cue_id/{cue.id}/networkPatchNumber', 2)
        elif cue.layer == 'audio':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'cyan')
        elif cue.layer == 'video':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'purple')
        # Per-type settings from the sync dialog win over the layer's
        if cue.colorName:
            self.q.send(f'/cue_id/{cue.id}/colorName', cue.colorName)
        if cue.customString:
            self.q.send(f'/cue_id/{cue.id}/customString', cue.customString)
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
