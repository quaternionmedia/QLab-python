from csv import DictReader
from time import sleep
from uuid import UUID

from pydantic import BaseModel, Field
from typing_extensions import Literal

from qlab import QLab

TYPES = Literal['Network', 'Midi', 'Video', 'Audio', 'Text']
LAYERS = Literal['Lights', 'Sound', 'Audio', 'Video', 'Music']

NAMES = {
    'Lights': '',
    'Sound': 's',
    'Video': 'v',
    'Music': 'm',
}


CUE_TYPES = {
    'Lights': 'Network',
    'Sound': 'Midi',
    'Video': 'Video',
    'Music': 'Audio',
    'Audio': 'Audio',
}


class Cue(BaseModel):
    id: UUID | None = Field(None, alias='uniqueID')
    type: TYPES

    layer: LAYERS | None = Field(None, alias='Layer Title')

    number: str | None = Field(None, alias='Cue Number')
    name: str | None = Field(None, alias='Label')
    notes: str | None = None


def open_csv(csv):
    with open(csv, 'r') as f:
        reader = DictReader(f)
        return list(reader)


def parse_cuelist(cuelist):
    """Parse a QLab cuelist into a dictionary of cues"""
    parsed = {}
    for cue in cuelist['cues']:
        print('parsing cue', cue)
        if not cue['number']:
            continue
        # cue['type'] = CUE_TYPES[cue['type']]
        parsed[cue['number']] = Cue(**cue)
    return parsed


class Cues:
    def __init__(self, csv: str):
        self.csv_cues = open_csv(csv)
        self.q = QLab()
        self.cuelists = self.q.send('/cueLists')['data']
        self.cues = parse_cuelist(self.cuelists[0])

    def sync_cuelist(self):
        """Synchronize the cuelist with the cues in the csv"""
        previous = (
            self.cuelists[0]['cues'][0]['uniqueID']
            if self.cuelists[0]['cues']
            else None
        )
        for cue in self.csv_cues:
            if not cue['Cue Number']:
                continue
            q = Cue(
                **cue,
                type=CUE_TYPES[cue['Layer Title']],
                notes=f'p{cue["Page Number"]}',
            )

            if q.number in self.cues:
                print('updating', q)
                previous = self.update_cue(q).id
            else:
                previous = self.create_cue(q, previous).id

    def update_cue(self, cue: Cue):
        """Update a cue"""
        if not cue.id:
            cue.id = self.q.get_cue_property(cue.number, 'uniqueID')
        (
            self.q.send(f'/cue_id/{cue.id}/number', value=cue.number)
            if cue.number
            else None
        )
        self.q.send(f'/cue_id/{cue.id}/name', value=cue.name) if cue.name else None
        self.q.send(f'/cue_id/{cue.id}/notes', value=cue.notes) if cue.notes else None
        return cue

    def create_cue(self, cue: Cue, previous: UUID = None):
        """Create a cue"""
        value = cue.type.lower()
        # TODO We should be able to send /new type [previous]
        # to create a new cue after the previous one, but it's not working.
        # if previous:
        #     value = [value, previous]
        cue.id = self.q.send(
            '/new',
            value,
        )['data']
        self.update_cue(cue)
        return cue
