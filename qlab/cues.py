from csv import DictReader

from qlab import QLab

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
        self.cues = open_csv(csv)
        self.q = QLab()
        self.cuelists = self.q.send('/cueLists')['data']
        self.cuelist = parse_cuelist(self.cuelists[0])

    def sync_cuelist(self):
        """Synchronize the cuelist with the cues in the csv"""
        for cue in self.cues:
            existing_cue = self.q.get_cue_property(cue['number'], 'number')
