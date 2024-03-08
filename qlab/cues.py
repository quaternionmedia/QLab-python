from csv import DictReader
from uuid import UUID

from pydantic import BaseModel, Field
from typing_extensions import Literal

from qlab import QLab

TYPES = Literal['Network', 'MIDI', 'Video', 'Audio', 'Text', 'Group']
LAYERS = Literal['Lights', 'Sound', 'Video', 'Music']

NOTE_ON = 0x90

LAYER_IDS = {
    'Lights': '',
    'Sound': 's',
    'Video': 'v',
    'Music': 'a',
}


CUE_TYPES = {
    'Lights': 'Network',
    'Sound': 'Group',
    'MIDI': 'MIDI',
    'Video': 'Video',
    'Music': 'Audio',
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
        if cue.get('cues'):
            # print('nested cuelist', cue)
            parsed.update(parse_cuelist(cue))
        # print('parsing cue', cue)
        if not cue['number']:
            continue
        parsed[cue['number']] = Cue(**cue)
    return parsed


class Cues:
    def __init__(self, csv: str, channels: dict = {}, **kwargs):
        self.csv_cues = open_csv(csv)
        self.channels = channels
        self.q = QLab(**kwargs)
        self.get_cuelists()

    def get_cuelists(self):
        self.cuelists = self.q.send('/cueLists')['data']
        self.cues = parse_cuelist(self.cuelists[0])

    def sync_cuelist(self):
        """Synchronize the cuelist with the cues in the csv"""
        # Refresh the cuelists
        self.get_cuelists()
        previous = None
        for cue in self.csv_cues:
            if not cue['Cue Number']:
                continue
            cue_type = CUE_TYPES[cue['Layer Title']]
            cue_layer = cue['Layer Title']
            cue_number = LAYER_IDS[cue_layer] + cue['Cue Number']
            q = Cue(
                **cue,
                type=cue_type,
                notes=f'p{ int(cue["Page Number"]) + 1 }',
            )
            q.number = cue_number

            if q.number in self.cues:
                print('updating', q)
                previous = self.update_cue(q).id
            else:
                print('creating cue', cue, q)
                previous = self.create_cue(q, previous).id

    def update_cue(self, cue: Cue):
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
            self.q.send(f'/cue_id/{cue.id}/customString', f'/eos/cue/{cue.number}/fire')
            self.q.send(f'/cue_id/{cue.id}/colorName', 'purple')
        elif cue.layer == 'Sound':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'blue')
            self.sound_cue(cue)
            self.q.send(f'/cue_id/{cue.id}/midiNote', 127)
        elif cue.layer == 'Music':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'green')
        elif cue.layer == 'Video':
            self.q.send(f'/cue_id/{cue.id}/colorName', 'orange')
        return cue

    def sound_cue(self, cue: Cue):
        if not cue.name.startswith(('mute', 'unmute')):
            raise ValueError('Sound cues must begin with "mute" or "unmute"', cue)
        action = cue.name.split(' ')[0]
        mute = action == 'mute'
        targets = cue.name.split(' ')[1:]
        print('sound cue', action, targets)
        for n, target in enumerate(targets):
            if f's{cue.id}.{n}' not in self.cues:
                sound_cue = self.create_cue(
                    Cue(type='MIDI', number=f's{cue.number}.{n}'), previous=cue.id
                )
                self.q.send(f'/move/{sound_cue.id}', [n, cue.id])
                self.q.send(
                    f'/cue_id/{sound_cue.id}/byte1', NOTE_ON | self.channels[target]
                )
                self.q.send(f'/cue_id/{sound_cue.id}/byte2', 127 if mute else 1)
                self.q.send(f'/cue_id/{sound_cue.id}/name', f'{action} {target}')

    def create_cue(self, cue: Cue, previous: UUID = None):
        """Create a cue"""
        value = cue.type.lower()
        # TODO We should be able to send /new type [previous]
        # to create a new cue after the previous one, but it's not working.
        if previous:
            value = [value, previous]
        cue.id = self.q.send(
            '/new',
            value,
        )['data']
        self.update_cue(cue)
        return cue
