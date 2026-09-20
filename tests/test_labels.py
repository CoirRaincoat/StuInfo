import copy
import sqlite3

import pytest

from friendbook.core import Store, atomic_json, new_record
from friendbook.labels import record_labels, with_labels
from friendbook.management import ManagementSession


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / 'labels.sqlite3')
    yield store
    store.close()


def test_legacy_group_and_both_remark_fields_survive_import_and_restart(store, tmp_path):
    legacy = dict(new_record(), group='旧同学', tags=['原标签', '阅读'], notes='原详细备注',
                  custom={'籍贯': '原籍贯'})
    legacy.pop('labels')  # Actual old archives do not contain the new field.
    archive = tmp_path / 'legacy.json'
    atomic_json(archive, dict(schema=1, active=[legacy], trash=[]))
    store.import_file(archive)
    store.reload()
    current = store.record(legacy['id'])
    assert record_labels(current) == ['旧同学']
    assert {key: current[key] for key in legacy} == legacy
    assert store.label_names() == ['旧同学']
    assert store.records(group='旧同学') == [current]


def test_multiple_labels_search_counts_merge_and_dissolve(store):
    a = with_labels(dict(new_record(), name='A'), ['同学', '球友', '同学'])
    b = with_labels(dict(new_record(), name='B'), ['同学'])
    c = new_record()
    for record in (a, b, c):
        store.save(record)
    store.create_label('尚未使用')
    store.reload()
    assert store.group_counts() == {'同学': 2, '球友': 1, '尚未使用': 0, '': 1}
    assert store.records(group='球友') == [a]
    assert store.records(query='球友') == [a]
    assert store.records(group='') == [c]
    assert store.rename_group('同学', '球友') == 2
    assert record_labels(store.record(a['id'])) == ['球友']
    assert store.group_counts()['球友'] == 2
    assert '同学' not in store.label_names()
    store.dissolve_group('球友')
    assert store.group_counts() == {'尚未使用': 0, '': 3}
    assert store.overview()['groups'] == store.group_counts()


def test_label_catalog_roundtrips_empty_labels_and_recycled_friends(store, tmp_path):
    record = with_labels(new_record(), ['待删除', '保留'])
    store.save(record)
    store.delete(record['id'])
    store.create_label('空标签')
    store.rename_group('待删除', '改名')
    store.dissolve_group('保留')
    assert record_labels(store.record(record['id'], trash=True)) == ['改名']
    backup = tmp_path / 'backup.json'
    store.export(backup, backup=True)
    before = store.payload()
    store.create_label('备份之后')
    store.recover(backup)
    assert store.payload() == before
    store.restore_item(record['id'])
    assert store.label_names() == ['改名', '空标签']
    store.reload()
    assert store.group_counts() == {'改名': 1, '空标签': 0}


def test_import_preview_preserves_empty_catalog(store, tmp_path):
    archive = tmp_path / 'catalog.json'
    atomic_json(archive, dict(schema=1, active=[], trash=[], label_catalog=['未使用']))
    preview = store.preview_import(archive)
    store.import_prepared(preview['records'], preview['label_catalog'])
    store.reload()
    assert store.label_names() == ['未使用']


def test_management_cancel_does_not_write_any_database_changes(store):
    records = [dict(new_record(), name=str(index)) for index in range(4)]
    for record in records:
        store.save(record)
    before, revision = store.payload(), store.revision
    writes = []
    store.db.set_trace_callback(writes.append)
    draft = ManagementSession(store)
    assert not draft.dirty
    draft.batch_update([records[0]['id']], 'favorite', True)
    draft.batch_update([records[0]['id']], 'labels', ['同学', '球友'])
    draft.batch_update([records[1]['id']], 'delete')
    draft.move_many([records[3]['id']], records[0]['id'])
    draft.create_label('空标签')
    assert draft.dirty and draft.book.validate()
    assert store.payload() == before and store.revision == revision
    draft.close()  # Cancelling/discarding a draft has no persistence operation.
    assert writes == []
    store.reload()
    assert store.payload() == before


def test_management_commits_all_operations_in_one_revision_and_preserves_unselected(store):
    records = [dict(new_record(), name=str(index)) for index in range(4)]
    for record in records:
        store.save(record)
    original = copy.deepcopy(records[2])
    draft = ManagementSession(store)
    draft.batch_update([records[0]['id']], 'favorite', True)
    draft.batch_update([records[1]['id']], 'delete')
    draft.move_many([records[3]['id']], records[0]['id'])
    draft.create_label('稍后使用')
    payload = draft.payload()
    store.commit_management(payload, draft.base_revision)
    assert store.revision == draft.base_revision + 1
    assert store.payload() == payload
    assert store.record(records[2]['id']) == original
    store.reload()
    assert store.payload() == payload


def test_management_failed_commit_and_external_conflict_keep_draft(store):
    record = new_record()
    store.save(record)
    original = store.payload()
    draft = ManagementSession(store)
    draft.batch_update([record['id']], 'favorite', True)
    proposed = draft.payload()
    store.db.execute('PRAGMA query_only=ON')
    with pytest.raises(sqlite3.OperationalError):
        store.commit_management(proposed, draft.base_revision)
    assert store.payload() == original and draft.payload() == proposed
    store.db.execute('PRAGMA query_only=OFF')
    other = Store(store.path)
    try:
        other.create_label('另一个窗口')
        with pytest.raises(ValueError, match='另一窗口'):
            store.commit_management(proposed, draft.base_revision)
        assert store.payload() == original and draft.payload() == proposed
        store.reload()
        with pytest.raises(ValueError, match='另一窗口'):
            store.commit_management(proposed, draft.base_revision)
        assert store.label_names() == ['另一个窗口']
        assert not store.record(record['id'])['favorite']
    finally:
        other.close()


def test_export_management_uses_draft_without_committing(store, tmp_path):
    record = new_record()
    store.save(record)
    before = store.payload()
    draft = ManagementSession(store)
    draft.batch_update([record['id']], 'labels', ['暂存标签'])
    path = tmp_path / 'draft-export.json'
    assert store.export_management_selected(path, [record['id']], draft.payload()) == 1
    imported, _ = Store.read_archive(path)
    assert record_labels(imported.get(record['id'])) == ['暂存标签']
    assert store.payload() == before
    with pytest.raises(ValueError):
        store.export_management_selected(store.path, [record['id']], draft.payload())


def test_invalid_labels_cannot_partially_change_catalog_or_records(store):
    record = new_record()
    store.save(record)
    before = store.payload()
    with pytest.raises(ValueError):
        store.batch_update([record['id']], 'labels', ['有效', 123])
    with pytest.raises(ValueError):
        store.commit_management(dict(before, label_catalog=['有效', 123]), store.revision)
    assert store.payload() == before
