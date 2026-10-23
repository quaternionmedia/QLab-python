"""Layer-type mapping in Cues.sync_show_cues (no QLab connection needed)."""

from types import SimpleNamespace

from qlab.cues import Cues, QLabCue, TypeMapping, render_osc, unknown_cue_types


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


def test_plugin_cue_type_falls_back_to_layer_type():
    c = make_cues()
    cue = show_cue('Projector')
    cue.cue_type = 'TheatreMix'  # set by a third-party plugin; not a QLab type
    synced = c.sync_show_cues([cue], {'Projector': 'video'})
    assert synced[0].type == 'Video'


def test_qlab_cue_type_is_kept():
    c = make_cues()
    cue = show_cue('Fx Sound')
    cue.cue_type = 'MIDI'
    synced = c.sync_show_cues([cue], {'Fx Sound': 'sound'})
    assert synced[0].type == 'MIDI'


def test_type_override_wins_over_layer_type():
    c = make_cues()
    cue = show_cue('Projector')
    cue.cue_type = 'TheatreMix'
    mapping = {'TheatreMix': TypeMapping(type='Audio')}
    synced = c.sync_show_cues([cue], {'Projector': 'video'}, mapping)
    assert synced[0].type == 'Audio'


def test_unknown_cue_types_counts_only_non_qlab_types():
    cues = [SimpleNamespace(cue_type=t) for t in ['TheatreMix', 'TheatreMix', 'MIDI', None]]
    assert unknown_cue_types(cues) == {'TheatreMix': 2}


def test_type_mapping_sets_colour_and_osc_after_layer_colour():
    c = make_cues()
    cue = show_cue('Projector')
    cue.cue_type = 'TheatreMix'
    m = TypeMapping(type='Network', color='red', osc='/tm/{number}/{name}')
    c.sync_show_cues([cue], {'Projector': 'video'}, {'TheatreMix': m})
    assert ('/cue_id/uuid-1/customString', '/tm/v42/Cue') in c.q.sent
    assert [v for k, v in c.q.sent if k.endswith('/colorName')][-1] == 'red'


def test_render_osc_fills_known_placeholders_only():
    cue = QLabCue(type='Network', number='s42', name='Fog', layer='sound')
    assert render_osc('/x/{number}/{layer}/{bogus}', cue) == '/x/s42/sound/{bogus}'


def test_sync_follows_script_order(tmp_path, monkeypatch):
    from sqlmodel import SQLModel
    from showrunner import models
    from showrunner.database import ShowDatabase

    import qlab.showrunner as sr

    db = ShowDatabase(tmp_path / 'show.db')
    SQLModel.metadata.create_all(db.engine)
    with db.session() as s:
        show = models.Show(name='Test')
        s.add(show)
        s.commit()
        cue_list = models.CueList(show_id=show.id)
        s.add(cue_list)
        s.add(models.Layer(show_id=show.id, name='Lights', type='lights'))
        s.commit()
        s.add_all([
            models.Cue(cue_list_id=cue_list.id, number='1', layer='Lights', script_line=30),
            models.Cue(cue_list_id=cue_list.id, number='2', layer='Lights', script_line=10,
                       script_char=5),
            models.Cue(cue_list_id=cue_list.id, number='3', layer='Lights', script_line=10,
                       script_char=0),
            models.Cue(cue_list_id=cue_list.id, number='4', layer='Lights'),  # unpositioned
        ])
        s.commit()
        cue_list_id = cue_list.id

    monkeypatch.setattr(sr, 'get_db', lambda: db)

    class Recorder:
        def __init__(self):
            self.numbers = []

        def sync_show_cues(self, show_cues, layer_types, types):
            self.numbers = [c.number for c in show_cues]
            return []

    cues = Recorder()
    sr.sync_cue_list(cues, cue_list_id)
    assert cues.numbers == ['3', '2', '1', '4']
