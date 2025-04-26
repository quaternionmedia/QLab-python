from csv import DictReader
from uuid import UUID

from pydantic import BaseModel, Field
from typing_extensions import Literal

from qlab import QLab

# QLab cue types
QLAB_TYPES = Literal['Network', 'MIDI', 'Video', 'Audio', 'Text', 'Group', 'Cue List', 'Cart', 'Fade']

# CueList layer types
LAYERS = Literal['Lights', 'Sound', 'Video', 'Audio', 'Stage']

NOTE_ON = 0x90

LAYER_IDS = {
    'Lights': '',
    'Sound': 's',
    'Video': 'v',
    'Audio': 'a',
}


CUE_TYPES = {
    'Lights': 'Network',
    'Sound': 'Network',
    'MIDI': 'MIDI',
    'Video': 'Video',
    'Audio': 'Audio',
    'Stage': 'Network'
}


class Cue(BaseModel):
    """Abstract cue from a csv export from CueList

    Attributes:
        Page Number
        Layer Title
        Cue Number
        Label
        Work Note
    """

    page: int | None = Field(None, alias='Page Number')
    layer: LAYERS | None = Field(None, alias='Layer Title')
    number: str | None = Field(None, alias='Cue Number')
    name: str | None = Field(None, alias='Label')
    notes: str | None = Field(None, alias='Work Note')


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


def open_csv(csv: str) -> list[Cue]:
    with open(csv, 'r') as f:
        reader = DictReader(f)
        return [Cue(**l) for l in list(reader)]


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
        self.cues = self.get_cuelists()

    def get_cuelists(self):
        data = self.q.send('/cueLists')['data']
        cuelists = [QLabCue(**cuelist) for cuelist in data]
        return flatten_cuelist(cuelists[0])

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
        elif cue.layer == 'Sound':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'blue')
            self.q.send(f'/cue_id/{cue.id}/customString', f'/jump {cue.number.replace("s", "")}')
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
