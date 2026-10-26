"""Layer-type mapping in Cues.sync_show_cues (no QLab connection needed)."""

from types import SimpleNamespace

import pytest

from qlab.cues import (
    Cues,
    LayerInfo,
    MissingPatch,
    QLabCue,
    TypeMapping,
    patch_numbers,
    render_osc,
    unknown_cue_types,
)


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
        layer=layer, cue_type=None, number=number, point=0, name='Cue', notes=None,
        external_id=None,
    )


def test_sound_type_gets_prefix_and_jump():
    c = make_cues()
    synced = c.sync_show_cues([show_cue('Fx Sound')], {'Fx Sound': LayerInfo('sound', 's')})
    assert synced[0].number == 's42'
    assert synced[0].type == 'Network'
    assert ('/cue_id/uuid-1/customString', '/jump 42') in c.q.sent


def test_layer_prefix_comes_from_the_layer_not_its_type():
    # a Sound layer whose prefix the user set to FX: QLab numbers follow the layer's config
    c = make_cues()
    synced = c.sync_show_cues([show_cue('Fx Sound')], {'Fx Sound': LayerInfo('sound', 'FX')})
    assert synced[0].number == 'FX42'


def test_video_type_gets_v_prefix_and_video_cue():
    c = make_cues()
    synced = c.sync_show_cues([show_cue('Projector')], {'Projector': LayerInfo('video', 'v')})
    assert synced[0].number == 'v42'
    assert synced[0].type == 'Video'


def test_unknown_layer_falls_back_to_generic():
    c = make_cues()
    synced = c.sync_show_cues([show_cue('Gone')], {})
    assert synced[0].number == 'Gone42'  # the layer's name is its prefix
    assert synced[0].type == 'Network'


def test_plugin_cue_type_falls_back_to_layer_type():
    c = make_cues()
    cue = show_cue('Projector')
    cue.cue_type = 'TheatreMix'  # set by a third-party plugin; not a QLab type
    synced = c.sync_show_cues([cue], {'Projector': LayerInfo('video', 'v')})
    assert synced[0].type == 'Video'


def test_qlab_cue_type_is_kept():
    c = make_cues()
    cue = show_cue('Fx Sound')
    cue.cue_type = 'MIDI'
    synced = c.sync_show_cues([cue], {'Fx Sound': LayerInfo('sound', 's')})
    assert synced[0].type == 'MIDI'


def test_type_override_wins_over_layer_type():
    c = make_cues()
    cue = show_cue('Projector')
    cue.cue_type = 'TheatreMix'
    mapping = {'TheatreMix': TypeMapping(type='Audio')}
    synced = c.sync_show_cues([cue], {'Projector': LayerInfo('video', 'v')}, mapping)
    assert synced[0].type == 'Audio'


def test_unknown_cue_types_counts_only_non_qlab_types():
    cues = [SimpleNamespace(cue_type=t) for t in ['TheatreMix', 'TheatreMix', 'MIDI', None]]
    assert unknown_cue_types(cues) == {'TheatreMix': 2}


def test_type_mapping_sets_colour_and_osc_after_layer_colour():
    c = make_cues()
    cue = show_cue('Projector')
    cue.cue_type = 'TheatreMix'
    m = TypeMapping(type='Network', prefix='v', color='red', osc='/tm/{prefix}{number}/{name}')
    c.sync_show_cues([cue], {'Projector': LayerInfo('video', 'v')}, {'TheatreMix': m})
    assert ('/cue_id/uuid-1/customString', '/tm/v42/Cue') in c.q.sent
    assert [v for k, v in c.q.sent if k.endswith('/colorName')][-1] == 'red'


def test_render_osc_fills_known_placeholders_only():
    cue = QLabCue(type='Network', number='s42', name='Fog', layer='sound')
    assert render_osc('/x/{number}/{layer}/{bogus}', cue, '42', 's') == '/x/42/sound/{bogus}'
    assert render_osc('/{prefix}{number}/{name}', cue, '42', 's') == '/s42/Fog'


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

        def sync_show_cues(self, show_cues, layer_types, types, patches, type_patches, links=None):
            self.numbers = [c.number for c in show_cues]
            return []

    cues = Recorder()
    sr.sync_cue_list(cues, cue_list_id)
    assert cues.numbers == ['3', '2', '1', '4']


def test_silent_qlab_times_out_instead_of_blocking(monkeypatch):
    # A QLab that accepts but never replies must fail fast, or shutdown waits on it forever
    import socket

    import qlab.osc
    from qlab import QLab

    monkeypatch.setattr(qlab.osc, 'REPLY_TIMEOUT', 0.2)
    server = socket.create_server(('127.0.0.1', 0))
    try:
        port = server.getsockname()[1]
        with pytest.raises(TimeoutError):
            QLab('127.0.0.1', port)  # its /alwaysReply is never answered
    finally:
        server.close()


def _fake_qlab(late=(), late_delay=0.6):
    """A QLab on localhost: answers each request, but drops one identical to the request before
    it that arrives under 0.1 s later (as the real QLab does), and answers the first request of
    each address in *late* only after *late_delay* seconds."""
    import json
    import socket
    import threading
    import time

    server = socket.create_server(('127.0.0.1', 0))
    late = set(late)
    last = {'frame': None, 'at': 0.0}
    lock = threading.Lock()

    def serve(conn):
        buf = b''
        while chunk := conn.recv(65536):
            buf += chunk
            while buf.count(b'\xc0') >= 2:
                frame, _, buf = buf[buf.index(b'\xc0') + 1:].partition(b'\xc0')
                with lock:
                    repeat = frame == last['frame'] and time.time() - last['at'] < 0.1
                    last['frame'], last['at'] = frame, time.time()
                if repeat:
                    continue
                address = frame.split(b'\x00')[0].decode()
                if address in late:
                    late.discard(address)
                    time.sleep(late_delay)
                body = json.dumps({'address': address, 'status': 'ok', 'data': address})
                payload = (address + body).encode()
                payload += b'\x00' * ((4 - len(payload) % 4) % 4 or 4)
                conn.sendall(b'\xc0' + payload + b'\xc0')

    def accept_forever():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            threading.Thread(target=serve, args=(conn,), daemon=True).start()

    threading.Thread(target=accept_forever, daemon=True).start()
    return server


def test_repeated_request_is_not_dropped_by_qlab(monkeypatch):
    # QLab ignores a request identical to the one just before it; the client waits between them
    import qlab.osc
    from qlab import QLab

    monkeypatch.setattr(qlab.osc, 'REPLY_TIMEOUT', 1.0)
    server = _fake_qlab()
    try:
        q = QLab('127.0.0.1', server.getsockname()[1])
        for _ in range(3):
            assert q.send('/workspaces')['address'] == '/workspaces'
        q.close()
    finally:
        server.close()


def test_late_reply_after_timeout_does_not_answer_the_next_request(monkeypatch):
    # QLab answers /cueLists after the client gave up; that reply must not be read as /workspaces
    import time

    import qlab.osc
    from qlab import QLab

    monkeypatch.setattr(qlab.osc, 'REPLY_TIMEOUT', 0.2)
    server = _fake_qlab(late={'/cueLists'}, late_delay=0.6)
    try:
        q = QLab('127.0.0.1', server.getsockname()[1])
        with pytest.raises(TimeoutError):
            q.send('/cueLists')
        time.sleep(0.6)  # the late /cueLists reply has arrived by now
        assert q.send('/workspaces')['address'] == '/workspaces'
        q.close()
    finally:
        server.close()


def test_lights_and_sound_set_no_patch_unless_chosen():
    c = make_cues()
    c.sync_show_cues([show_cue('Lights'), show_cue('Fx Sound')], {'Lights': LayerInfo('lights', ''), 'Fx Sound': LayerInfo('sound', 's')})
    assert not [k for k, _ in c.q.sent if k.endswith('/networkPatchNumber')]


def test_chosen_patch_number_is_sent_for_its_layer():
    c = make_cues()
    c.sync_show_cues(
        [show_cue('Fx Sound')], {'Fx Sound': LayerInfo('sound', 's')}, patches={'Fx Sound': 2}
    )
    assert ('/cue_id/uuid-1/networkPatchNumber', 2) in c.q.sent


def test_patch_for_another_layer_is_not_sent():
    c = make_cues()
    c.sync_show_cues([show_cue('Lights')], {'Lights': LayerInfo('lights', '')}, patches={'Fx Sound': 2})
    assert not [k for k, _ in c.q.sent if k.endswith('/networkPatchNumber')]


PATCHES = [{'uniqueID': 'ion-id', 'name': 'Ion'}, {'uniqueID': 'tm-id', 'name': 'TheatreMix'}]


def test_patch_numbers_follow_list_position_and_skip_none():
    chosen = {'Lights': 'ion-id', 'Fx Sound': 'tm-id', 'Stage': None}
    assert patch_numbers(PATCHES, chosen) == {'Lights': 1, 'Fx Sound': 2}


def test_patch_not_in_qlab_is_reported_by_layer():
    with pytest.raises(MissingPatch) as e:
        patch_numbers(PATCHES, {'Lights': 'gone-id', 'Fx Sound': 'tm-id'})
    assert e.value.layers == ['Lights']


def test_saved_patch_round_trips_and_sync_uses_its_number(tmp_path, monkeypatch):
    from sqlmodel import SQLModel
    from showrunner import models
    from showrunner.database import ShowDatabase

    import qlab.showrunner as sr
    from qlab.showrunner import NetworkPatch, SavedChoices

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
        s.add(models.Cue(cue_list_id=cue_list.id, number='1', layer='Lights'))
        s.commit()
        show_id, cue_list_id = show.id, cue_list.id

    monkeypatch.setattr(sr, 'get_db', lambda: db)
    saved = SavedChoices(
        layers={'Lights': NetworkPatch(uniqueID='tm-id', name='TheatreMix'), 'Fx': None},
        cue_types={'TheatreMix': NetworkPatch(uniqueID='ion-id', name='Ion')},
        cue_type_prefixes={'TheatreMix': 'tm'},
    )
    sr.save_choices(show_id, saved)
    assert sr.load_choices(show_id) == saved

    class FakeQ:
        def network_patches(self):
            return PATCHES

    class Recorder:
        q = FakeQ()
        patches = None

        def sync_show_cues(self, show_cues, layer_types, types, patches, type_patches, links=None):
            self.patches = patches
            return []

    cues = Recorder()
    sr.sync_cue_list(cues, cue_list_id, patches={'Lights': 'tm-id'})
    assert cues.patches == {'Lights': 2}

    with pytest.raises(MissingPatch):
        sr.sync_cue_list(cues, cue_list_id, patches={'Lights': 'gone-id'})


def test_mapped_network_type_takes_the_patch_from_its_mapping():
    c = make_cues()
    cue = show_cue('Projector')
    cue.cue_type = 'TheatreMix'
    mapping = {'TheatreMix': TypeMapping(type='Network', patch='tm-id')}
    c.sync_show_cues([cue], {'Projector': LayerInfo('video', 'v')}, mapping, type_patches={'TheatreMix': 3})
    assert ('/cue_id/uuid-1/networkPatchNumber', 3) in c.q.sent


def test_mapped_type_without_patch_is_not_given_its_layers_patch():
    c = make_cues()
    cue = show_cue('Lights')
    cue.cue_type = 'TheatreMix'
    mapping = {'TheatreMix': TypeMapping(type='Network')}
    c.sync_show_cues([cue], {'Lights': LayerInfo('lights', '')}, mapping, patches={'Lights': 1})
    assert not [k for k, _ in c.q.sent if k.endswith('/networkPatchNumber')]


def test_non_network_cue_on_a_network_layer_gets_no_patch():
    c = make_cues()
    cue = show_cue('Lights')
    cue.cue_type = 'MIDI'
    c.sync_show_cues([cue], {'Lights': LayerInfo('lights', '')}, patches={'Lights': 1})
    assert not [k for k, _ in c.q.sent if k.endswith('/networkPatchNumber')]


def test_sync_resolves_mapped_type_patch_to_its_number(tmp_path, monkeypatch):
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
        s.add(models.Layer(show_id=show.id, name='Projector', type='video'))
        s.commit()
        s.add(models.Cue(cue_list_id=cue_list.id, number='1', layer='Projector',
                         cue_type='TheatreMix'))
        s.commit()
        cue_list_id = cue_list.id

    monkeypatch.setattr(sr, 'get_db', lambda: db)

    class FakeQ:
        def network_patches(self):
            return PATCHES

    class Recorder:
        q = FakeQ()
        type_patches = None

        def sync_show_cues(self, show_cues, layer_types, types, patches, type_patches, links=None):
            self.type_patches = type_patches
            return []

    cues = Recorder()
    types = {'TheatreMix': TypeMapping(type='Network', prefix='tm', patch='tm-id')}
    sr.sync_cue_list(cues, cue_list_id, types=types)
    assert cues.type_patches == {'TheatreMix': 2}


def test_mapped_type_is_numbered_with_its_own_prefix():
    c = make_cues()
    cue = show_cue('Projector')
    cue.cue_type = 'TheatreMix'
    mapping = {'TheatreMix': TypeMapping(type='Network', prefix='tm')}
    synced = c.sync_show_cues([cue], {'Projector': LayerInfo('video', 'v')}, mapping)
    assert synced[0].number == 'tm42'


def test_sync_refuses_an_unknown_type_without_a_prefix(tmp_path, monkeypatch):
    from sqlmodel import SQLModel
    from showrunner import models
    from showrunner.database import ShowDatabase

    import qlab.showrunner as sr
    from qlab.cues import MissingPrefix

    db = ShowDatabase(tmp_path / 'show.db')
    SQLModel.metadata.create_all(db.engine)
    with db.session() as s:
        show = models.Show(name='Test')
        s.add(show)
        s.commit()
        cue_list = models.CueList(show_id=show.id)
        s.add(cue_list)
        s.add(models.Layer(show_id=show.id, name='Projector', type='video'))
        s.commit()
        s.add(models.Cue(cue_list_id=cue_list.id, number='1', layer='Projector',
                         cue_type='TheatreMix'))
        s.commit()
        cue_list_id = cue_list.id

    monkeypatch.setattr(sr, 'get_db', lambda: db)

    class Unused:
        def sync_show_cues(self, *args):
            raise AssertionError('must not sync without a prefix')

    types = {'TheatreMix': TypeMapping(type='Network', prefix='')}
    with pytest.raises(MissingPrefix) as e:
        sr.sync_cue_list(Unused(), cue_list_id, types=types)
    assert e.value.types == ['TheatreMix']
