"""A generic ShowRunner layer (its own name as prefix) syncs cue and group numbers both ways."""

pytest_plugins = ['test_group_sync']  # provides the show_db fixture

from showrunner.groups import create_group, update_group
from showrunner.layers import add_layer
from showrunner.models import Cue, CueGroup
from test_group_sync import U, cue_list_tree, make_cues, qcue

from qlab import group_sync
from qlab import showrunner as qlab_showrunner


def _add_q_layer(db):
    with db.session() as s:
        add_layer(s, 1, 'Q', 'generic', 'grey')
        s.commit()


def _qlab_nodes(fake, type_=None):
    out = []

    def walk(items):
        for n in items or []:
            if type_ is None or n.get('type') == type_:
                out.append(n)
            walk(n.get('cues'))
    walk(fake.tree[0]['cues'])
    return out


def _cue(db, cue_id):
    with db.session() as s:
        c = s.get(Cue, cue_id)
        return c.number, c.point, c.layer, c.external_id, c.external_number


def _group(db, gid):
    with db.session() as s:
        g = s.get(CueGroup, gid)
        return g.number, g.layer, g.external_id


def test_new_cue_on_generic_layer_is_sent_with_its_layer_prefix(show_db):
    _add_q_layer(show_db)
    with show_db.session() as s:
        s.add(Cue(cue_list_id=1, number='5', layer='Q', script_line=3))
        s.commit()
    cues, fake = make_cues(cue_list_tree())
    qlab_showrunner.sync_with_groups(cues, 1)
    assert 'Q5' in [n['number'] for n in _qlab_nodes(fake)]
    assert _cue(show_db, 3)[3] is not None  # linked to the QLab cue it made
    assert _cue(show_db, 3)[4] == 'Q5'


def test_renumber_on_generic_layer_moves_the_linked_qlab_cue(show_db):
    _add_q_layer(show_db)
    with show_db.session() as s:
        s.add(Cue(cue_list_id=1, number='5', layer='Q', script_line=3, external_id=U(50),
                  external_number='Q5'))
        s.commit()
    cues, fake = make_cues(cue_list_tree(qcue(50, number='Q5', name='a')))
    with show_db.session() as s:
        s.get(Cue, 3).number = '6'
        s.commit()
    qlab_showrunner.sync_with_groups(cues, 1)
    nodes = _qlab_nodes(fake)
    assert [n['number'] for n in nodes if n['uniqueID'] == U(50)] == ['Q6']
    assert len(nodes) == 3  # the two Lights cues plus the one Q cue: no duplicate
    assert _cue(show_db, 3)[4] == 'Q6'


def test_qlab_renumber_on_generic_layer_is_pulled(show_db):
    _add_q_layer(show_db)
    with show_db.session() as s:
        s.add(Cue(cue_list_id=1, number='5', layer='Q', script_line=3, external_id=U(50),
                  external_number='Q5'))
        s.commit()
    cues, _ = make_cues(cue_list_tree(qcue(50, number='Q9', name='a')))
    qlab_showrunner.sync_with_groups(cues, 1)
    assert _cue(show_db, 3)[:3] == ('9', 0, 'Q')


def test_group_number_on_generic_layer_is_pushed(show_db):
    _add_q_layer(show_db)
    with show_db.session() as s:
        g = create_group(s, 1, [], name='Act', layer='Q', number='7')
        gid = g.id
        s.commit()
    group_sync.record_change('create', {'id': gid, 'external_id': None})
    cues, fake = make_cues(cue_list_tree())
    qlab_showrunner.sync_with_groups(cues, 1)
    groups = _qlab_nodes(fake, 'Group')
    assert [g['number'] for g in groups] == ['Q7']
    assert _group(show_db, gid)[2] == groups[0]['uniqueID']


def test_group_number_changed_in_showrunner_is_pushed(show_db):
    _add_q_layer(show_db)
    with show_db.session() as s:
        g = create_group(s, 1, [], name='Act', layer='Q', number='7')
        gid = g.id
        s.commit()
    group_sync.record_change('create', {'id': gid, 'external_id': None})
    cues, fake = make_cues(cue_list_tree())
    qlab_showrunner.sync_with_groups(cues, 1)
    with show_db.session() as s:
        update_group(s, gid, number='8')
        s.commit()
    group_sync.record_change('update', {'id': gid, 'external_id': None})
    qlab_showrunner.sync_with_groups(cues, 1)
    assert [g['number'] for g in _qlab_nodes(fake, 'Group')] == ['Q8']


def test_group_number_changed_in_qlab_is_pulled(show_db):
    _add_q_layer(show_db)
    with show_db.session() as s:
        g = create_group(s, 1, [], name='Act', layer='Q', number='7')
        g.external_id = U(60)
        gid = g.id
        s.commit()
    cues, _ = make_cues(cue_list_tree(qcue(60, number='Q9', type_='Group', name='Act')))
    qlab_showrunner.sync_with_groups(cues, 1)
    assert _group(show_db, gid)[:2] == ('9', 'Q')


def test_qlab_only_child_of_generic_layer_group_becomes_an_orphan_cue(show_db):
    _add_q_layer(show_db)
    with show_db.session() as s:
        s.add(Cue(cue_list_id=1, number='1', layer='Q', script_line=3))
        s.commit()
        known = s.query(Cue).filter(Cue.layer == 'Q').one().id
    tree = cue_list_tree(qcue(60, number='Q9', type_='Group', name='Act',
                              children=[qcue(71, number='Q1', name='known'),
                                        qcue(70, number='Q4', name='new')]))
    cues, _ = make_cues(tree)
    report = group_sync.pull(cues, 1, {'Q1': known}, sync_orphans=True)
    assert report.orphans_created == 1
    with show_db.session() as s:
        assert [(c.number, c.layer) for c in s.query(Cue).filter(Cue.external_id == U(70))] == [
            ('4', 'Q')]
