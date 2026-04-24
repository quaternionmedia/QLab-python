from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from typing_extensions import Literal

from cuelist import CUE_TYPES, LAYER_IDS, LAYERS, Cue, open_csv
from qlab import QLab

# QLab cue types
QLAB_TYPES = Literal[
    'Network', 'MIDI', 'Video', 'Audio', 'Text', 'Group', 'Cue List', 'Cart', 'Fade'
]

NOTE_ON = 0x90


class QLabCue(BaseModel):
    """QLab cue"""

    id: UUID | None = Field(None, alias='uniqueID')
    type: QLAB_TYPES
    layer: LAYERS | None = None

    number: str | None = None
    name: str | None = None
    notes: str | None = None
    cues: list['QLabCue'] | None = None
    colorName: str | None = None
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
    def __init__(self, channels: dict = {}, **kwargs):
        self.channels = channels
        self.q = QLab(**kwargs)
        self.cuelists = self.get_cuelists()
        self.cues: dict[str, QLabCue] = {}
        for cl in self.cuelists:
            if cl.cues:
                self.cues.update(flatten_cuelist(cl))

    def get_cuelists(self):
        data = self.q.send('/cueLists')['data']
        return [QLabCueList(**cuelist) for cuelist in data]

    def sync_cuelist(self, csv: str):
        """Synchronize the cuelist with the cues in the csv"""
        csv_cues = open_csv(csv)
        previous = None
        for cue in csv_cues:
            if not cue.number:
                continue
            q = QLabCue(**cue.model_dump(), type=CUE_TYPES[cue.layer])
            q.number = f'{LAYER_IDS[cue.layer]}{cue.number}'
            q.notes = f'p{ cue.page }{" - " + cue.notes if cue.notes else ""}'

            if q.number in self.cues:
                print('updating', q)
                previous = self.update_cue(q).id
            else:
                print('creating cue', cue, q)
                previous = self.create_cue(q, previous).id

    def sync_show_cues(self, show_cues: list) -> list[QLabCue]:
        """Sync ShowRunner Cue models to QLab.

        Converts each ShowRunner Cue into a QLabCue (applying layer prefixes
        and cue-type mapping) then creates or updates the cue in QLab.

        Args:
            show_cues: List of ShowRunner Cue model instances.

        Returns:
            List of QLabCue objects that were synced.
        """
        synced: list[QLabCue] = []
        previous = None
        for cue in show_cues:
            if not cue.layer:
                continue
            cue_type = cue.cue_type or CUE_TYPES.get(cue.layer, 'Network')
            layer_prefix = LAYER_IDS.get(cue.layer, '')
            cue_number = str(cue.number)
            if cue.point:
                cue_number += f'.{cue.point}'
            qlab_number = f'{layer_prefix}{cue_number}'

            q = QLabCue(
                type=cue_type,
                layer=cue.layer,
                number=qlab_number,
                name=cue.name,
                notes=cue.notes,
            )

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
        if cue.layer == 'Lights':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'orange')
            self.q.send(f'/cue_id/{cue.id}/customString', f'/eos/cue/{cue.number}/fire')
            self.q.send(f'/cue_id/{cue.id}/networkPatchNumber', 1)
        elif cue.layer == 'Sound':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'blue')
            self.q.send(
                f'/cue_id/{cue.id}/customString', f'/jump {cue.number.replace("s", "")}'
            )
            self.q.send(f'/cue_id/{cue.id}/networkPatchNumber', 2)
        elif cue.layer == 'Audio':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'cyan')
        elif cue.layer == 'Video':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'purple')
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
