from csv import DictReader
from uuid import UUID

from pydantic import BaseModel

from qlab import QLab


class Cue(BaseModel):
    uniqueID: UUID

    number: str
    name: str
    type: str
    notes: str | None = None


NAMES = {
    'Lights': '',
    'Sound': 's',
    'Video': 'v',
    'Music': 'm',
}


def open_csv(csv):
    with open(csv, 'r') as f:
        reader = DictReader(f)
        return list(reader)


def parse_cuelist(cuelist):
    """Parse the cuelist into a dictionary of cues"""
    parsed = {}
    for cue in cuelist['cues']:
        parsed[cue['number']] = cue
    return parsed


class Cues:
    def __init__(self, csv):
        self.csv_cues = open_csv(csv)
        self.q = QLab()
        self.cuelists = self.q.send('/cueLists')['data']
        self.cues = parse_cuelist(self.cuelists[0])

    def sync_cuelist(self):
        """Synchronize the cuelist with the cues in the csv"""
        for cue in self.csv_cues:
            if cue['number'] in self.cues:
                self.update_cue(cue)
            else:
                self.create_cue(cue)

    def update_cue(self, cue):
        """Update a cue"""
        pass

    def create_cue(self, cue):
        """Create a cue"""
        pass
