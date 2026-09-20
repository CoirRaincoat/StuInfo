import copy
import json
import random
import sqlite3
import pytest
from friendbook.core import Store, new_record
from friendbook.contact_fields import grouped_contacts, contact_caption


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / 'batch.sqlite3')
    for index in range(8):
        store.save(dict(new_record(), name=str(index), custom={'籍贯': '虚构地点'},
                        contacts={'电话1': 'demo-1', '电话2': 'demo-2', 'QQ': 'demo-qq'}))
    yield store
    store.close()


def test_batch_is_one_transaction_and_preserves_unselected(store):
    original = copy.deepcopy(store.payload())
    ids = [r['id'] for r in store.records()]
    revision = store.revision
    assert store.batch_update(ids[1:3], 'favorite', True) == 2
    assert store.revision == revision + 1
    assert store.record(ids[0]) == original['active'][0]
    assert store.record(ids[1])['favorite'] and store.record(ids[1])['version'] == 2
    store.batch_update(ids[1:3], 'group', '新分组')
    assert store.record(ids[2])['group'] == '新分组'
    store.batch_update(ids[1:3], 'delete')
    store.reload()
    assert store.counts() == (6, 2)
    assert store.record(ids[1], True)['custom'] == {'籍贯': '虚构地点'}
    assert store.record(ids[0]) == original['active'][0]


def test_bulk_validation_and_failure_are_atomic(store):
    before = copy.deepcopy(store.payload())
    uid = store.records()[0]['id']
    for ids in ([], [uid, uid], [uid, 'missing']):
        with pytest.raises(ValueError):
            store.batch_update(ids, 'delete')
    with pytest.raises(ValueError):
        store.move_many([uid], uid)
    with pytest.raises(ValueError):
        store.move_many([uid], 'missing')
    store.db.execute('PRAGMA query_only=ON')
    for method, args in ((store.batch_update, ([uid], 'delete')), (store.move_many, ([uid], None))):
        with pytest.raises(sqlite3.OperationalError):
            method(*args)
        assert store.payload() == before
    store.db.execute('PRAGMA query_only=OFF')
    store.reload()
    assert store.payload() == before


def test_noncontiguous_reorder_against_sequence_reference(store):
    order = [r['id'] for r in store.records()]
    rng = random.Random(43)
    for _ in range(60):
        chosen = rng.sample(order, rng.randint(1, len(order)))
        selected = [uid for uid in order if uid in chosen]
        rest = [uid for uid in order if uid not in chosen]
        at = rng.randrange(len(rest) + 1)
        anchor = rest[at] if at < len(rest) else None
        store.move_many(chosen, anchor)
        order = rest[:at] + selected + rest[at:]
        assert [r['id'] for r in store.book] == order
        assert store.book.validate()
        store.reload()
        assert [r['id'] for r in store.book] == order


def test_selected_export_roundtrip_uses_original_order(store, tmp_path):
    records = store.records()
    path = tmp_path / 'selected.json'
    store.export_selected(path, [records[3]['id'], records[0]['id']])
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['schema'] == 1 and data['trash'] == []
    assert data['active'] == [records[0], records[3]]
    before = path.read_bytes()
    with pytest.raises(ValueError):
        store.export_selected(path, ['absent'])
    assert path.read_bytes() == before
    with pytest.raises(ValueError):
        store.export_selected(store.path, [records[0]['id']])
    other = Store(tmp_path / 'other.sqlite3')
    try:
        assert other.import_file(path) == (2, 0)
        assert other.records() == [records[0], records[3]]
    finally:
        other.close()


def test_contact_grouping_and_labels_are_lossless():
    original = {'手机': '1', '工作电话': '2', 'QQ2': '3', '微信': '4', '邮箱': '5', '自定义平台': '6'}
    groups = grouped_contacts(original)
    assert groups['电话'] == [('手机', '1'), ('工作电话', '2')]
    assert dict(entry for entries in groups.values() for entry in entries) == original
    assert contact_caption('电话', 0, 1, '电话2') == '电话'
    assert contact_caption('电话', 0, 2, '电话') == '电话1'
    assert contact_caption('电话', 0, 1, '工作电话') == '工作电话'
