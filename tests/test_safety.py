import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest
from friendbook.core import Store, new_record, atomic_json
import friendbook.core as core


def test_atomic_export_failure_keeps_previous_file(tmp_path, monkeypatch):
    path = tmp_path / 'export.json'
    path.write_text('original', encoding='utf-8')
    def fail(*args):
        raise PermissionError('injected replace failure')
    monkeypatch.setattr(core.os, 'replace', fail)
    with pytest.raises(PermissionError):
        atomic_json(path, {'schema': 1})
    assert path.read_text(encoding='utf-8') == 'original'
    assert not list(tmp_path.glob('.friendbook-*'))


def test_backup_failure_blocks_recovery(tmp_path, monkeypatch):
    store = Store(tmp_path / 'db.sqlite3')
    try:
        store.save(new_record())
        original = copy.deepcopy(store.payload())
        archive = tmp_path / 'archive.json'
        atomic_json(archive, dict(schema=1, active=[], trash=[]))
        def fail(*args, **kwargs):
            raise OSError('injected full disk')
        monkeypatch.setattr(store, 'export', fail)
        with pytest.raises(OSError):
            store.recover(archive)
        assert store.payload() == original
        store.reload()
        assert store.payload() == original
    finally:
        store.close()


def test_abrupt_process_exit_rolls_back_sqlite(tmp_path):
    path = tmp_path / 'db.sqlite3'
    store = Store(path)
    store.save(new_record())
    original = store.payload()
    code = "import sqlite3,os,sys; c=sqlite3.connect(sys.argv[1]); c.execute(\"UPDATE state SET payload='broken' WHERE id=1\"); os._exit(17)"
    result = subprocess.run([sys.executable, '-c', code, str(path)], timeout=15)
    assert result.returncode == 17
    store.reload()
    assert store.payload() == original
    store.close()


@pytest.mark.parametrize('payload', [
    {'schema': True, 'active': [], 'trash': []},
    {'schema': 99, 'active': [], 'trash': []},
    {'schema': 1, 'active': 'bad', 'trash': []},
])
def test_archive_shape(payload):
    with pytest.raises(ValueError):
        Store.decode(payload)


def test_duplicate_json_keys_rejected(tmp_path):
    path = tmp_path / 'duplicate.json'
    path.write_text('{"schema":1,"active":[],"trash":[],"active":[]}', encoding='utf-8')
    with pytest.raises(ValueError, match='重复字段'):
        Store.read_archive(path)


def test_failed_merge_restores_both_nodes(tmp_path):
    store = Store(tmp_path / 'db.sqlite3')
    a, b = new_record(), new_record()
    store.save(a)
    store.save(b)
    original = copy.deepcopy(store.payload())
    store.db.execute('PRAGMA query_only=ON')
    with pytest.raises(sqlite3.OperationalError):
        store.merge(a['id'], b['id'], a, 1)
    assert store.payload() == original
    store.close()


def test_capacity_guard_prevents_unrestorable_data(tmp_path, monkeypatch):
    store = Store(tmp_path / 'db.sqlite3')
    original = store.payload()
    monkeypatch.setattr(core, 'MAX_FILE', 100)
    with pytest.raises(ValueError, match='容量限制'):
        store.save(new_record())
    assert store.payload() == original
    store.close()


def test_commit_failure_rolls_back_candidate_and_transaction(tmp_path):
    store = Store(tmp_path / 'db.sqlite3')
    store.save(new_record())
    before = copy.deepcopy(store.payload())
    actual = store.db
    class FailingCommit:
        def __getattr__(self, name):
            return getattr(actual, name)

        def commit(self):
            raise sqlite3.OperationalError('injected commit failure')
    store.db = FailingCommit()
    with pytest.raises(sqlite3.OperationalError):
        store.save(new_record())
    assert store.payload() == before
    store.db = actual
    store.reload()
    assert store.payload() == before
    store.close()
