"""QLab group sync: tree parsing, number mapping, pull, push, delete order.

FakeQLab keeps a cue tree in memory and applies move/delete/new like QLab would, so the
sync code runs against a real-looking tree. The OSC addresses are the unverified ones (see
Cues.move_cue); a scratch-workspace spike must confirm them before live use.
"""

import copy
from types import SimpleNamespace

import pytest
from showrunner.database import ShowDatabase
from showrunner.groups import create_group
from showrunner.layers import add_layer
from showrunner.models import Cue, CueGroup, CueList, Show
from sqlmodel import select

from qlab import group_sync
from qlab import showrunner as qlab_showrunner
from qlab.cues import (
    Cues,
    QLabCue,
    QLabCueList,
    TypeMapping,
    group_qlab_number,
    group_tree,
    show_qlab_number,
)


def U(n: int) -> str:
    return f'00000000-0000-0000-0000-{n:012d}'


def qcue(n, number=None, name=None, type_='Network', children=None, color=None):
    d = {'uniqueID': U(n), 'type': type_, 'number': number, 'name': name, 'colorName': color}
    if children is not None:
        d['cues'] = children
    return d


class FakeQLab:
    """Applies move/delete/new/name/colour to a cue-list tree of dicts."""

    def __init__(self, cuelists):
        self.tree = cuelists
        self.sent = []
        self.next_id = 100

    def _find(self, uid):
        """(containing list, index, node) for the cue with *uid*."""
        def walk(items):
            for i, node in enumerate(items):
                if node['uniqueID'] == uid:
                    return items, i, node
                if node.get('cues') is not None:
                    found = walk(node['cues'])
                    if found:
                        return found
            return None
        for cl in self.tree:
            found = walk(cl['cues'])
            if found:
                return found
        raise KeyError(uid)

    def _container(self, parent):
        if parent == self.tree[0]['uniqueID']:  # the cue list itself
            return self.tree[0]['cues']
        return self._find(parent)[2]['cues']

    def send(self, message='/go', value=None):
        self.sent.append((message, value))
        if message.startswith('/workspace/ws/move/') and len(value or []) < 2:
            # QLab 5.6.3 rejects an index without a parent (spike)
            return {'address': message, 'status': 'error', 'data': None}
        return {'address': message, 'status': 'ok', 'data': self._apply(message, value)}

    def _apply(self, message, value):
        if message == '/cueLists':
            return copy.deepcopy(self.tree)
        if message == '/workspaces':
            return [{'uniqueID': 'ws'}]
        if message == '/new':
            self.next_id += 1
            uid = U(self.next_id)
            kind = value if isinstance(value, str) else value[0]  # value may be [type, previous]
            node = {'uniqueID': uid, 'type': 'Group', 'cues': []} if kind == 'group' else {
                'uniqueID': uid, 'type': 'Network', 'number': None, 'name': None}
            self.tree[0]['cues'].append(node)
            return uid
        if message.startswith('/cue_id/'):
            node = self._find(message.split('/')[2])[2]
            if message.endswith('/name'):
                node['name'] = value
            elif message.endswith('/colorName'):
                node['colorName'] = value
            elif message.endswith('/number'):
                node['number'] = value
            return None
        if message.startswith('/workspace/ws/move/'):
            uid = message.rsplit('/', 1)[1]
            index, parent = value[0], value[1]
            container, _, node = self._find(uid)
            container.remove(node)
            target = self._container(parent)
            target.insert(min(index, len(target)), node)
            return None
        if message.startswith('/workspace/ws/delete_id/'):
            # QLab deletes a group together with its children
            uid = message.rsplit('/', 1)[1]
            container, _, node = self._find(uid)
            container.remove(node)
            return None
        raise AssertionError(f'unexpected message {message}')


def make_cues(tree) -> tuple[Cues, FakeQLab]:
    fake = FakeQLab(tree)
    cues = Cues(fake)
    return cues, fake


def cue_list_tree(*children):
    return [{'uniqueID': U(1), 'type': 'Cue List', 'cues': list(children)}]


# --- tree parsing and numbers ------------------------------------------------------------

def test_group_tree_keeps_nesting_order_and_members():
    tree = cue_list_tree(
        qcue(2, type_='Group', name='Outer', color='red', children=[
            qcue(3, number='1', name='a'),
            qcue(4, type_='Group', name='Inner', children=[qcue(5, number='2', name='b')]),
            qcue(6, number='3', name='c'),
        ]),
        qcue(7, number='4', name='loose'),
    )
    groups = group_tree([QLabCueList(**d) for d in tree])
    outer, inner = groups
    assert [g['uid'] for g in groups] == [U(2), U(4)]
    assert outer['parent'] is None and outer['index'] == 0 and outer['color'] == 'red'
    assert outer['children'] == [U(3), U(4), U(6)]
    assert [m.number for m in outer['members']] == ['1', '3']
    assert inner['parent'] == U(2) and inner['index'] == 1
    assert [m.number for m in inner['members']] == ['2']


def test_show_qlab_number_uses_layer_prefix_or_type_mapping():
    lights = SimpleNamespace(layer='Lights', cue_type=None, number=42, point=0)
    sound = SimpleNamespace(layer='Sound', cue_type=None, number=7, point=2)
    mapped = SimpleNamespace(layer='Projector', cue_type='TheatreMix', number=3, point=0)
    layer_types = {'Lights': 'lights', 'Sound': 'sound', 'Projector': 'video'}
    overrides = {'TheatreMix': TypeMapping(type='Network', prefix='m')}
    assert show_qlab_number(lights, layer_types) == '42'
    assert show_qlab_number(sound, layer_types) == 's7.2'
    assert show_qlab_number(mapped, layer_types, overrides) == 'm3'


def test_move_cue_sends_index_and_parent_and_keeps_zero():
    cues, fake = make_cues(cue_list_tree(qcue(2, type_='Group', children=[]), qcue(9, number='0')))
    cues.move_cue(U(9), 0, U(2))
    cues.move_cue(U(9), 0, U(1))  # back to the cue list: the list uniqueID is the parent
    assert ('/workspace/ws/move/' + U(9), [0, U(2)]) in fake.sent
    assert ('/workspace/ws/move/' + U(9), [0, U(1)]) in fake.sent
    assert [c['uniqueID'] for c in fake.tree[0]['cues']] == [U(9), U(2)]


def test_new_group_sets_name_and_colour():
    cues, fake = make_cues(cue_list_tree())
    uid = cues.new_group('Act 1', 'orange')
    assert ('/cue_id/%s/name' % uid, 'Act 1') in fake.sent
    assert ('/cue_id/%s/colorName' % uid, 'orange') in fake.sent


def test_group_number_takes_layer_prefix_like_a_cue():
    layer_types = {'Lights': 'lights', 'Sound': 'sound'}
    assert group_qlab_number('5', 'Sound', layer_types) == 's5'
    assert group_qlab_number('5', 'Lights', layer_types) == '5'
    assert group_qlab_number(None, 'Sound', layer_types) == ''
    cues, fake = make_cues(cue_list_tree())
    uid = cues.new_group('Act 1', 'orange', 's5')
    assert ('/cue_id/%s/number' % uid, 's5') in fake.sent


# --- ShowRunner side: DB fixture ------------------------------------------------------------

@pytest.fixture()
def show_db(tmp_path, monkeypatch):
    db = ShowDatabase(tmp_path / 'sync.db')
    db.create_schema()
    monkeypatch.setattr(group_sync, 'get_db', lambda: db)
    monkeypatch.setattr(qlab_showrunner, 'get_db', lambda: db)
    with db.session() as s:
        s.add(Show(name='Hamlet'))
        s.commit()
        add_layer(s, 1, 'Lights', 'lights', 'orange')
        s.add(CueList(show_id=1, name='Main'))
        s.commit()
        s.add(Cue(cue_list_id=1, number='1', layer='Lights', script_line=1))
        s.add(Cue(cue_list_id=1, number='2', layer='Lights', script_line=2))
        s.commit()
    group_sync.dirty.clear()
    group_sync.pending_deletes.clear()
    yield db
    db.close()


NUMBERS = {'1': 1, '2': 2}


def test_pull_creates_group_and_counts_orphans(show_db):
    tree = cue_list_tree(qcue(2, type_='Group', name='Act', color='red', children=[
        qcue(3, number='1'), qcue(4, number='99'),
    ]))
    cues, _ = make_cues(tree)
    report = group_sync.pull(cues, 1, NUMBERS)
    assert report.created_groups == 1 and report.orphans_skipped == 1
    with show_db.session() as s:
        g = s.exec(select(CueGroup)).one()
        assert (g.external_id, g.name, g.color) == (U(2), 'Act', 'red')
        assert [c.id for c in s.exec(select(Cue).where(Cue.group_id == g.id))] == [1]


def test_pull_with_sync_orphans_creates_only_cues_that_keep_their_number(show_db):
    tree = cue_list_tree(qcue(2, type_='Group', children=[
        qcue(3, number='1'), qcue(4, number='7', name='new'), qcue(5, number='q8'),
    ]))
    cues, _ = make_cues(tree)
    report = group_sync.pull(cues, 1, NUMBERS, sync_orphans=True)
    # '7' is a Lights cue number; 'q8' would need a prefix no layer gives, so it is skipped
    assert (report.orphans_created, report.orphans_skipped) == (1, 1)
    with show_db.session() as s:
        made = s.exec(select(Cue).where(Cue.number == '7')).one()
        assert (made.layer, made.name) == ('Lights', 'new')


def test_pull_empties_existing_group_whose_cues_left_it_in_qlab(show_db):
    with show_db.session() as s:
        g = create_group(s, 1, [1, 2], name='Act')
        g.external_id = U(2)
        s.commit()
    tree = cue_list_tree(qcue(2, type_='Group', name='Act', children=[qcue(3, number='99')]))
    cues, _ = make_cues(tree)
    group_sync.pull(cues, 1, NUMBERS)
    with show_db.session() as s:
        assert s.exec(select(CueGroup)).one().external_id == U(2)
        assert s.exec(select(Cue).where(Cue.group_id.is_not(None))).all() == []


def test_pull_removes_group_deleted_in_qlab_and_keeps_its_cues(show_db):
    with show_db.session() as s:
        create_group(s, 1, [1, 2], name='Gone').external_id = U(50)
        s.commit()
    cues, _ = make_cues(cue_list_tree())
    report = group_sync.pull(cues, 1, NUMBERS)
    assert report.removed_groups == 1
    with show_db.session() as s:
        assert s.exec(select(CueGroup)).all() == []
        assert len(s.exec(select(Cue).where(Cue.cue_list_id == 1)).all()) == 2


def test_pull_leaves_dirty_group_alone_and_reports_conflict(show_db):
    with show_db.session() as s:
        g = create_group(s, 1, [1], name='Mine')
        g.external_id = U(2)
        s.commit()
        gid = g.id
    group_sync.dirty.add(gid)
    tree = cue_list_tree(qcue(2, type_='Group', name='Theirs', children=[qcue(3, number='2')]))
    cues, _ = make_cues(tree)
    report = group_sync.pull(cues, 1, NUMBERS, skip_uids=frozenset({U(2)}))
    assert report.conflicts == ['Theirs']
    with show_db.session() as s:
        assert s.get(CueGroup, gid).name == 'Mine'


def test_push_creates_group_in_qlab_then_moves_members(show_db):
    with show_db.session() as s:
        create_group(s, 1, [1, 2], name='Scene', color='blue')
        s.commit()
    group_sync.dirty.add(1)
    tree = cue_list_tree(qcue(3, number='1'), qcue(4, number='2'))
    cues, fake = make_cues(tree)
    synced = [QLabCue(uniqueID=U(3), type='Network', number='1'),
              QLabCue(uniqueID=U(4), type='Network', number='2')]
    report = group_sync.push(cues, 1, NUMBERS, {q.number: str(q.id) for q in synced})
    assert report.created_groups == 1 and report.pushed == 1
    with show_db.session() as s:
        assert s.get(CueGroup, 1).external_id == U(101)  # the id FakeQLab gives /new
    # both members moved into the new group, in order
    moves = [m for m, _ in fake.sent if m.startswith('/workspace/ws/move/')]
    assert len(moves) == 2
    assert group_sync.dirty == set()


def test_delete_ungroups_children_before_deleting_the_group(show_db):
    tree = cue_list_tree(
        qcue(9, number='0'),
        qcue(2, type_='Group', name='Act', children=[qcue(3, number='1'), qcue(4, number='2')]),
        qcue(10, number='5'),
    )
    cues, fake = make_cues(tree)
    group_sync.record_change('delete', {'id': 1, 'external_id': U(2), 'name': 'Act'})
    assert group_sync.apply_pending_deletes(cues) == 1
    # group gone, children now sit where it was, in order, and nothing else moved
    names = [c['uniqueID'] for c in fake.tree[0]['cues']]
    assert names == [U(9), U(3), U(4), U(10)]
    deletes = [m for m, _ in fake.sent if m.startswith('/workspace/ws/delete')]
    assert deletes == ['/workspace/ws/delete_id/' + U(2)]


def test_hook_queues_changes_without_qlab_io():
    from qlab.showrunner import plugin

    group_sync.dirty.clear()
    group_sync.pending_deletes.clear()
    plugin.showrunner_group_changed('members', {'id': 4, 'external_id': U(2)}, None)
    plugin.showrunner_group_changed('delete', {'id': 5, 'external_id': U(3)}, None)
    assert group_sync.dirty == {4}
    assert [g['id'] for g in group_sync.pending_deletes] == [5]
    group_sync.dirty.clear()
    group_sync.pending_deletes.clear()


def test_push_updates_existing_group_and_takes_removed_cues_out(show_db):
    with show_db.session() as s:
        g = create_group(s, 1, [1, 2], name='Renamed', color='teal')
        g.external_id = U(2)
        s.commit()
        gid = g.id
    group_sync.dirty.add(gid)
    tree = cue_list_tree(
        qcue(2, type_='Group', name='Old', children=[qcue(3, number='1')]),  # cue 2 is missing
        qcue(4, number='2'),  # cue 2 sits outside the group in QLab
    )
    cues, fake = make_cues(tree)
    synced_uids = {'1': U(3), '2': U(4)}
    report = group_sync.push(cues, 1, NUMBERS, synced_uids)
    assert report.created_groups == 0 and report.pushed == 1
    # name and colour updated on the existing group
    assert ('/cue_id/%s/name' % U(2), 'Renamed') in fake.sent
    assert ('/cue_id/%s/colorName' % U(2), 'teal') in fake.sent
    # cue 2 joins the group: the move's new parent is the group
    assert ('/workspace/ws/move/%s' % U(4), [1, U(2)]) in fake.sent
    assert group_sync.dirty == set()


def test_push_removed_member_goes_back_before_its_group(show_db):
    with show_db.session() as s:
        g = create_group(s, 1, [1], name='Act')
        g.external_id = U(2)
        s.commit()
    group_sync.dirty.add(1)
    tree = cue_list_tree(
        qcue(9, number='0'),
        qcue(2, type_='Group', name='Act', children=[qcue(3, number='1'), qcue(4, number='2')]),
    )
    cues, fake = make_cues(tree)
    group_sync.push(cues, 1, NUMBERS, {'1': U(3), '2': U(4)})
    # cue 2 is no longer in the ShowRunner group: it is moved out, to the group's position
    assert ('/workspace/ws/move/%s' % U(4), [1, U(1)]) in fake.sent
    assert [c['uniqueID'] for c in fake.tree[0]['cues']] == [U(9), U(4), U(2)]


def test_push_leaves_qlab_only_child_in_its_group(show_db):
    with show_db.session() as s:
        g = create_group(s, 1, [1], name='Act')
        g.external_id = U(2)
        s.commit()
    group_sync.dirty.add(1)
    # U(77) is a QLab cue with no ShowRunner counterpart: it must not be ejected
    tree = cue_list_tree(qcue(2, type_='Group', name='Act', children=[
        qcue(3, number='1'), qcue(77, number='q9')]))
    cues, fake = make_cues(tree)
    group_sync.push(cues, 1, NUMBERS, {'1': U(3), '2': U(4)})
    assert [c['uniqueID'] for c in fake.tree[0]['cues'][0]['cues']] == [U(3), U(77)]


def test_failed_delete_stays_queued_for_the_next_sync(show_db):
    tree = cue_list_tree(qcue(2, type_='Group', children=[qcue(3, number='1')]))
    cues, fake = make_cues(tree)
    group_sync.record_change('delete', {'id': 1, 'external_id': U(2), 'name': 'Act'})

    def refuse(uid):
        raise RuntimeError('QLab is busy')
    cues.delete_cue = refuse
    with pytest.raises(RuntimeError):
        group_sync.apply_pending_deletes(cues)
    assert [g['id'] for g in group_sync.pending_deletes] == [1]
    group_sync.pending_deletes.clear()


def test_qlab_no_colour_maps_to_grey():
    from qlab.group_sync import _colour
    assert _colour('none') == 'grey' and _colour(None) == 'grey' and _colour('') == 'grey'
    assert _colour('orange') == 'orange'


# --- cue numbers: renumbers go both ways on the same QLab cue ---------------------------

def _link(db, cue_id, uid, number):
    with db.session() as s:
        c = s.get(Cue, cue_id)
        c.external_id, c.external_number = uid, number
        s.add(c)
        s.commit()


def _renumber_showrunner(db, cue_id, number):
    with db.session() as s:
        c = s.get(Cue, cue_id)
        c.number = number
        s.add(c)
        s.commit()


def _cue(db, cue_id):
    with db.session() as s:
        c = s.get(Cue, cue_id)
        return c.number, c.point, c.group_id, c.external_id, c.external_number


def test_renumber_in_showrunner_moves_the_same_qlab_cue(show_db):
    cues, fake = make_cues(cue_list_tree(qcue(50, number='1', name='a')))
    _link(show_db, 1, U(50), '1')
    _renumber_showrunner(show_db, 1, '5')
    qlab_sync_result = qlab_showrunner.sync_with_groups(cues, 1)
    assert qlab_sync_result['synced'] == 2
    nodes = fake.tree[0]['cues']
    assert [n['number'] for n in nodes if n['uniqueID'] == U(50)] == ['5']  # no duplicate
    assert not any(n.get('number') == '1' for n in nodes)
    assert _cue(show_db, 1)[3:] == (U(50), '5')


def test_renumber_in_qlab_is_pulled_into_showrunner(show_db):
    cues, fake = make_cues(cue_list_tree(qcue(50, number='7', name='a')))  # renumbered in QLab
    _link(show_db, 1, U(50), '1')  # last synced as 1
    qlab_showrunner.sync_with_groups(cues, 1)
    assert _cue(show_db, 1)[:2] == ('7', 0)
    assert _cue(show_db, 1)[3:] == (U(50), '7')
    assert [n['uniqueID'] for n in fake.tree[0]['cues']].count(U(50)) == 1


def test_group_keeps_a_cue_renumbered_in_showrunner(show_db):
    tree = cue_list_tree(qcue(60, type_='Group', name='Act', children=[qcue(50, number='1')]))
    cues, _ = make_cues(tree)
    _link(show_db, 1, U(50), '1')
    with show_db.session() as s:
        g = CueGroup(cue_list_id=1, name='Act', color='grey', external_id=U(60))
        s.add(g)
        s.flush()
        c = s.get(Cue, 1)
        c.group_id, c.number = g.id, '5'
        s.add(c)
        s.commit()
        gid = g.id
    result = qlab_showrunner.sync_with_groups(cues, 1)
    assert _cue(show_db, 1)[2] == gid
    assert result['groups']['pulled']['orphans_skipped'] == 0


def test_number_changed_on_both_sides_keeps_showrunner_and_reports(show_db):
    cues, fake = make_cues(cue_list_tree(qcue(50, number='7', name='a')))
    _link(show_db, 1, U(50), '1')
    _renumber_showrunner(show_db, 1, '5')
    result = qlab_showrunner.sync_with_groups(cues, 1)
    assert _cue(show_db, 1)[:2] == ('5', 0)
    assert [n['number'] for n in fake.tree[0]['cues'] if n['uniqueID'] == U(50)] == ['5']
    assert any('both' in c for c in result['groups']['pulled']['conflicts'])


def test_qlab_renumber_onto_a_taken_number_keeps_showrunner_and_reports(show_db):
    cues, fake = make_cues(cue_list_tree(qcue(50, number='2', name='a')))  # QLab moved it to 2
    _link(show_db, 1, U(50), '1')
    result = qlab_showrunner.sync_with_groups(cues, 1)
    assert _cue(show_db, 1)[:2] == ('1', 0)  # cue 2 already has number 2 in ShowRunner
    assert any('taken' in c for c in result['groups']['pulled']['conflicts'])
    assert [n['number'] for n in fake.tree[0]['cues'] if n['uniqueID'] == U(50)] == ['1']
