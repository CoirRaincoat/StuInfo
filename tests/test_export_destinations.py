"""Exports must never replace SQLite journals, application locks or settings."""
import json

import pytest

from friendbook.core import Store, new_record
from friendbook.management import ManagementSession


@pytest.fixture
def export_store(tmp_path):
    store = Store(tmp_path / 'friends.sqlite3')
    store.save(dict(new_record(), name='虚构导出演示'))
    yield store
    store.close()


@pytest.mark.parametrize('name', [
    'friends.sqlite3', 'friends.sqlite3-journal', 'friends.sqlite3-wal',
    'friends.sqlite3-shm', 'app.lock', 'settings.ini',
])
def test_export_policy_protects_reserved_files(export_store, tmp_path, name):
    destination = tmp_path / name
    if name != 'friends.sqlite3':
        destination.write_bytes(b'original reserved file')
    original = destination.read_bytes()
    for check in (export_store.check_export_destination, export_store._safe_destination):
        with pytest.raises(ValueError, match='不能覆盖'):
            check(destination)
    with pytest.raises(ValueError, match='不能覆盖'):
        export_store.export(destination, backup=True)
    assert destination.read_bytes() == original


def test_selected_and_management_exports_share_policy(export_store, tmp_path):
    uid = export_store.records()[0]['id']
    destination = tmp_path / 'settings.ini'
    destination.write_bytes(b'original settings')
    session = ManagementSession(export_store)
    for source in (export_store, session):
        with pytest.raises(ValueError, match='不能覆盖'):
            source.export_selected(destination, [uid])
    with pytest.raises(ValueError, match='不能覆盖'):
        export_store.export_management_selected(destination, [uid], session.payload())
    assert destination.read_bytes() == b'original settings'


def test_nonexistent_reserved_names_and_path_aliases_are_rejected(export_store, tmp_path):
    destination = tmp_path / 'friends.sqlite3-wal'
    assert not destination.exists()
    with pytest.raises(ValueError, match='不能覆盖'):
        export_store.check_export_destination(destination)
    nested = tmp_path / 'nested'
    nested.mkdir()
    with pytest.raises(ValueError, match='不能覆盖'):
        export_store.check_export_destination(nested / '..' / 'app.lock')
    assert not destination.exists()
    assert not (tmp_path / 'app.lock').exists()


def test_normal_export_and_same_name_in_another_directory_are_allowed(export_store, tmp_path):
    destination = tmp_path / 'backup.json'
    export_store.export(destination, backup=True)
    assert json.loads(destination.read_text(encoding='utf-8')) == export_store.payload()
    other = tmp_path / 'unrelated'
    other.mkdir()
    export_store.check_export_destination(other / 'settings.ini')
    export_store.check_export_destination(tmp_path / 'chart.png')
