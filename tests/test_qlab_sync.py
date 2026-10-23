"""Layer-type mapping in Cues.sync_show_cues (no QLab connection needed)."""

from types import SimpleNamespace

from qlab.cues import Cues


class FakeQLab:
    def __init__(self):
        self.sent = []

    def send(self, message='/go', value=None):
        self.sent.append((message, value))
        return {'data': 'uuid-1'}


def make_cues():
    c = Cues.__new__(Cues)  # skip __init__: it connects to QLab
    c.q = FakeQLab()
    c.cues = {}
    return c


def show_cue(layer, number='42'):
    return SimpleNamespace(
        layer=layer, cue_type=None, number=number, point=0, name='Cue', notes=None
    )


def test_sound_type_gets_prefix_and_jump():
    c = make_cues()
    synced = c.sync_show_cues([show_cue('Fx Sound')], {'Fx Sound': 'sound'})
    assert synced[0].number == 's42'
    assert synced[0].type == 'Network'
    assert ('/cue_id/uuid-1/customString', '/jump 42') in c.q.sent


def test_video_type_gets_v_prefix_and_video_cue():
    c = make_cues()
    synced = c.sync_show_cues([show_cue('Projector')], {'Projector': 'video'})
    assert synced[0].number == 'v42'
    assert synced[0].type == 'Video'


def test_unknown_layer_falls_back_to_generic():
    c = make_cues()
    synced = c.sync_show_cues([show_cue('Gone')], {})
    assert synced[0].number == '42'
    assert synced[0].type == 'Network'
