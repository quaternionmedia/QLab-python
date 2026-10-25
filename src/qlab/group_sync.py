"""Two-way sync of cue groups between ShowRunner and QLab Group cues.

A ShowRunner group carries its QLab Group cue's uniqueID in ``external_id``.
- Pull (QLab wins): QLab groups become ShowRunner groups. QLab-only children are skipped and
  counted, or created as cues when ``sync_orphans`` is set. Groups with unpushed ShowRunner
  changes are skipped and reported as conflicts.
- Push (ShowRunner wins): groups that are new or changed in ShowRunner since the last push
  (``dirty``) are written to QLab.
- Deletes made in ShowRunner are queued by ``record_change`` (no QLab I/O in the viewer's
  thread) and applied before the next pull: the group's children move out in QLab, then its
  empty Group cue is deleted, so the pull does not bring the group back.

shortcut: the queue and dirty set are in memory; a server restart drops unsynced group edits.
Persist them if group edits must survive a restart.
"""

import re
import threading
from dataclasses import asdict, dataclass, field

from showrunner.groups import (
    create_group,
    delete_group,
    group_depths,
    group_tree,
    set_members,
    update_group,
)
from showrunner.layers import get_layers
from showrunner.models import Cue, CueGroup, CueList
from showrunner.plugins.db import get_db
from sqlmodel import select

from qlab.cues import (
    CUE_TYPES,
    Cues,
    group_qlab_number,
    layer_prefix,
    qlab_cues_by_uid,
    qlab_prefix,
    show_qlab_number,
)
from qlab.cues import group_tree as qlab_group_tree

_lock = threading.Lock()
dirty: set[int] = set()  # ShowRunner group ids changed since their last push
pending_deletes: list[dict] = []  # snapshots of groups deleted in ShowRunner, not yet in QLab

_NUMBER = re.compile(r'^[A-Za-z]*(\d+)(?:\.(\d+))?$')


def record_change(action: str, group: dict) -> None:
    """Note a ShowRunner group change for the next sync. Never does QLab I/O."""
    with _lock:
        if action == 'delete':
            dirty.discard(group['id'])
            if group.get('external_id'):
                pending_deletes.append(group)
        else:
            dirty.add(group['id'])


@dataclass
class Report:
    pulled: int = 0
    renumbered: int = 0
    created_groups: int = 0
    removed_groups: int = 0
    orphans_created: int = 0
    orphans_skipped: int = 0
    conflicts: list[str] = field(default_factory=list)
    pushed: int = 0
    deleted: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _colour(colour: str | None) -> str:
    # QLab reports 'none' for a group with no colour
    return colour if isinstance(colour, str) and colour not in ('', 'none') else 'grey'


def unpushed_uids(session, cue_list_id: int) -> frozenset[str]:
    """QLab uniqueIDs of this list's groups changed in ShowRunner and not yet pushed."""
    with _lock:
        ids = list(dirty)
    if not ids:
        return frozenset()
    rows = session.exec(select(CueGroup.external_id).where(
        CueGroup.cue_list_id == cue_list_id, CueGroup.id.in_(ids)))
    return frozenset(uid for uid in rows if uid)


def _snapshot(cues: Cues) -> dict[str, dict]:
    """QLab's groups by uniqueID, read now: each move changes the indexes of the rest."""
    return {g['uid']: g for g in qlab_group_tree(cues.get_cuelists())}


def _container(node: dict) -> str:
    """The uniqueID a group's children are moved within: its parent group, or the cue list."""
    return node['parent'] or node['list']


def apply_pending_deletes(cues: Cues) -> int:
    """Ungroup each queued group in QLab, then delete its empty Group cue; returns the count.

    Children take the group's place in its parent, in order, so the rest of the list stays put.
    An entry leaves the queue only when done, so a QLab error keeps it for the next sync.
    """
    done = 0
    while True:
        with _lock:
            if not pending_deletes:
                break
            snap = pending_deletes[0]
        node = _snapshot(cues).get(snap['external_id'])
        if node is not None:  # None: already gone from QLab
            for offset, child in enumerate(node['children']):
                cues.move_cue(child, node['index'] + offset, _container(node))
            cues.delete_cue(node['uid'])
            done += 1
        with _lock:
            pending_deletes.pop(0)
    if done:
        cues.cuelists = cues.get_cuelists()  # the pull and push below must see the new order
    return done


def pull(
    cues: Cues,
    cue_list_id: int,
    numbers: dict[str, int],
    sync_orphans: bool = False,
    skip_uids: frozenset[str] = frozenset(),
) -> Report:
    """Make this cue list's ShowRunner groups match QLab's Group cues.

    *numbers* maps each QLab cue number of the list to its ShowRunner cue id. Groups whose
    QLab uniqueID is in *skip_uids* have unpushed ShowRunner changes and are left alone.
    """
    report = Report()
    tree = qlab_group_tree(cues.cuelists)
    by_uid = {g['uid']: g for g in tree}
    db = get_db()
    with db.session() as s:
        cl = s.get(CueList, cue_list_id)
        layers = get_layers(s, cl.show_id)
        existing = {
            g.external_id: g
            for g in s.exec(select(CueGroup).where(
                CueGroup.cue_list_id == cue_list_id, CueGroup.external_id.is_not(None)))
        }
        linked = {c.external_id: c.id for c in s.exec(select(Cue).where(
            Cue.cue_list_id == cue_list_id, Cue.external_id.is_not(None)))}

        def cue_for(m) -> int | None:
            """The ShowRunner cue of a QLab member: by its linked uniqueID, else by number."""
            return linked.get(m.id, numbers.get(m.number))

        def holds(uid: str) -> bool:
            """True if the QLab group, or a group inside it, has a cue of this list."""
            node = by_uid[uid]
            return any(cue_for(m) is not None for m in node['members']) or any(
                holds(c) for c in node['children'] if c in by_uid)

        group_of: dict[str, int] = {}  # QLab uid -> ShowRunner group id, once written
        for node in sorted(tree, key=lambda g: _depth(g, by_uid)):  # outer groups first
            uid = node['uid']
            if not holds(uid) and uid not in existing:
                continue  # a group for another cue list, or one with no cue in this list
            if uid in skip_uids:
                report.conflicts.append(node['name'] or uid)
                continue
            members = []
            for m in node['members']:
                if cue_for(m) is not None:
                    members.append(cue_for(m))
                elif sync_orphans and _create_orphan(s, cue_list_id, m, layers, numbers):
                    members.append(numbers[m.number])
                    report.orphans_created += 1
                else:
                    report.orphans_skipped += 1
            parent = node['parent']
            parent_row = existing.get(parent)  # a conflict-skipped parent keeps its group
            parent_id = group_of.get(parent) or (parent_row.id if parent_row else None)
            numbering = _group_number(node, layers, report)
            if uid in existing:
                g = existing[uid]
                g.parent_id = parent_id  # before set_members: cues it drops go to the parent
                _set_group(lambda **kw: update_group(s, g.id, **kw), node, numbering, report)
                set_members(s, g.id, members)
            else:
                g = _set_group(lambda **kw: create_group(
                    s, cue_list_id, members, parent_id=parent_id, **kw), node, numbering, report)
                g.external_id = uid
                report.created_groups += 1
            s.add(g)
            s.flush()
            group_of[uid] = g.id
            report.pulled += 1

        # Groups QLab no longer has were deleted there: delete them here too (cues stay)
        for ext, g in existing.items():
            if ext not in by_uid and ext not in skip_uids:
                delete_group(s, g.id)
                report.removed_groups += 1
        s.commit()
    return report


def pull_numbers(cues: Cues, cue_list_id: int, types: dict) -> Report:
    """Take cue numbers changed in QLab into ShowRunner, for cues linked to a QLab cue.

    A linked cue whose QLab number changed since the last sync, and whose ShowRunner number
    did not, takes the QLab number: its layer's prefix must match, the number must be digits
    (with an optional .point), and no other cue may hold it. Otherwise ShowRunner keeps its
    number, the sync writes it over the QLab change, and the case is reported. A change on
    both sides is ShowRunner's too.
    """
    report = Report()
    by_uid = qlab_cues_by_uid(cues.cuelists)
    db = get_db()
    with db.session() as s:
        layer_types = {x['name']: x['type'] for x in get_layers(
            s, s.get(CueList, cue_list_id).show_id)}
        linked = s.exec(select(Cue).where(
            Cue.cue_list_id == cue_list_id, Cue.external_id.is_not(None))).all()
        for c in linked:
            q = by_uid.get(c.external_id)
            if q is None or not q.number or q.number == c.external_number:
                continue  # gone from QLab (the sync re-creates it), or not changed there
            if show_qlab_number(c, layer_types, types) != c.external_number:
                report.conflicts.append(
                    f'cue {c.number_label} (renumbered in both; ShowRunner kept)')
                continue
            prefix = qlab_prefix(c, layer_types, types)
            digits = re.fullmatch(r'(\d+)(?:\.(\d+))?', q.number[len(prefix):])
            if not q.number.startswith(prefix) or not digits:
                report.conflicts.append(f'cue {c.number_label}: QLab number {q.number} is not '
                                        f'a {prefix or "plain"} number (ShowRunner kept)')
                continue
            number, point = digits.group(1), int(digits.group(2) or 0)
            clash = s.exec(select(Cue).where(
                Cue.cue_list_id == cue_list_id, Cue.layer == c.layer, Cue.number == number,
                Cue.point == point, Cue.id != c.id)).first()
            if clash:
                report.conflicts.append(f'cue {c.number_label}: QLab number {q.number} is taken '
                                        f'by {clash.number_label} (ShowRunner kept)')
                continue
            c.number, c.point, c.external_number = number, point, q.number
            s.add(c)
            report.renumbered += 1
        s.commit()
    return report


def _parse_group_number(qnum: str, layers: list[dict]) -> tuple[str, str] | None:
    """(layer, number) for a QLab group number, if exactly one layer's prefix it carries."""
    hits = []
    for x in layers:
        prefix = layer_prefix(x['name'], x['type'])
        rest = qnum[len(prefix):] if qnum.startswith(prefix) else ''
        if rest.isdigit():
            hits.append((x['name'], rest))
    return hits[0] if len(hits) == 1 else None


def _group_number(node: dict, layers: list[dict], report: Report) -> dict:
    """Layer and number to take from QLab's group number.

    Empty means QLab has none: keep ShowRunner's, since a number not yet pushed would be lost.
    """
    if not node['number']:
        return {}
    hit = _parse_group_number(node['number'], layers)
    if hit is None:
        report.conflicts.append(f"{node['name'] or node['uid']}: QLab number {node['number']} "
                                "is not a layer's number (ShowRunner kept)")
        return {}
    return {'layer': hit[0], 'number': hit[1]}


def _set_group(write, node: dict, numbering: dict, report: Report):
    """Write a group's name, colour and number; a number that clashes is kept as it was."""
    fields = dict(name=node['name'], color=_colour(node['color']))
    try:
        return write(**fields, **numbering)
    except ValueError as e:
        report.conflicts.append(f"{node['name'] or node['uid']}: {e} (ShowRunner kept)")
        return write(**fields)


def _depth(node: dict, by_uid: dict) -> int:
    depth = 0
    while node['parent'] in by_uid:
        node = by_uid[node['parent']]
        depth += 1
    return depth


def _create_orphan(session, cue_list_id: int, qcue, layers: list[dict], numbers: dict) -> bool:
    """Create the ShowRunner cue for a QLab-only child (sync option). False if it cannot be made.

    It must come out with the child's own QLab number, or the next sync would write a duplicate.
    """
    match = _NUMBER.match(qcue.number or '')
    if not match:
        return False
    layer_types = {x['name']: x['type'] for x in layers}
    for x in layers:
        if CUE_TYPES.get(x['type'], 'Network') != qcue.type:  # as sync_show_cues picks it
            continue
        cue = Cue(cue_list_id=cue_list_id, number=match.group(1), point=int(match.group(2) or 0),
                  name=qcue.name, layer=x['name'], notes=qcue.notes,
                  external_id=qcue.id, external_number=qcue.number)
        if show_qlab_number(cue, layer_types) == qcue.number:
            session.add(cue)
            session.flush()
            numbers[qcue.number] = cue.id
            return True
    return False


def push(cues: Cues, cue_list_id: int, numbers: dict[str, int], uids: dict[str, str]) -> Report:
    """Write new and dirty ShowRunner groups to QLab.

    *numbers* maps QLab cue numbers to ShowRunner cue ids; *uids* maps the QLab numbers the
    cue sync wrote to their uniqueIDs, so each member's QLab uniqueID is known.
    """
    report = Report()
    uid_of = {numbers[num]: uid for num, uid in uids.items() if num in numbers}
    known = set(uid_of.values())
    db = get_db()
    with db.session() as s:
        show_id = s.get(CueList, cue_list_id).show_id
        layer_types = {ly['name']: ly['type'] for ly in get_layers(s, show_id)}
        groups = group_tree(s, cue_list_id)
        depths = group_depths(groups)
        uid_of_group = {g['id']: g['external_id'] for g in groups if g['external_id']}
        for g in sorted(groups, key=lambda g: depths[g['id']]):  # parents first
            if g['external_id'] and g['id'] not in dirty:
                continue
            row = s.get(CueGroup, g['id'])
            qnum = group_qlab_number(g['number'], g['layer'], layer_types)
            if row.external_id is None:
                uid = cues.new_group(g['name'], g['color'], qnum)
                row.external_id = uid
                s.add(row)
                uid_of_group[g['id']] = uid
                report.created_groups += 1
            else:
                uid = row.external_id
                cues.set_group(uid, g['name'], g['color'], qnum)
            tree = _snapshot(cues)  # earlier groups' moves changed the indexes
            node = tree.get(uid, {'children': [], 'index': 0, 'parent': None, 'list': None})
            wanted = [uid_of[c] for c in g['cue_ids'] if c in uid_of]
            sub_groups = [uid_of_group[c['id']] for c in groups
                          if c['parent_id'] == g['id'] and c['id'] in uid_of_group]
            # only cues this sync knows: a QLab-only child stays where the QLab user put it
            removed = [c for c in node['children']
                       if c in known and c not in wanted and c not in sub_groups]
            for k, child in enumerate(removed):  # removed in ShowRunner: back out, before it
                cues.move_cue(child, node['index'] + k, _container(node))
            for i, cue_uid in enumerate(wanted):
                if cue_uid not in node['children']:
                    cues.move_cue(cue_uid, i, uid)
            tree = _snapshot(cues)  # the moves above shifted indexes, the group's own too
            node = tree[uid]
            parent_uid = uid_of_group.get(g['parent_id']) if g['parent_id'] else None
            if node['parent'] != parent_uid:
                if parent_uid:  # moved into a group: last in it
                    cues.move_cue(uid, len(tree.get(parent_uid, {'children': []})['children']),
                                  parent_uid)
                elif node['parent'] in tree:  # to the top: just after its old top-level ancestor
                    top = tree[node['parent']]
                    while top['parent']:
                        top = tree[top['parent']]
                    cues.move_cue(uid, top['index'] + 1, top['list'])
            s.commit()  # keep a new group's QLab uid even if a later group fails
            report.pushed += 1
            with _lock:
                dirty.discard(g['id'])
        s.commit()
    return report
