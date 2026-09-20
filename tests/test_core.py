import copy
import io
import json
import random
import sqlite3
import pytest
from PIL import Image
from friendbook.linked import LinkedBook
from friendbook.core import Store, new_record, validate_record, photo_bytes, atomic_json


def record(name='虚构好友', **fields):
    r = new_record()
    r.update(name=name, **fields)
    return r


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / 'friends.sqlite3')
    yield s
    s.close()


def test_linked_random_operations():
    rng = random.Random(18)
    book = LinkedBook()
    oracle = []
    for step in range(1800):
        operation = rng.choice(['insert', 'remove', 'move', 'update']) if oracle else 'insert'
        if operation == 'insert':
            r = record(str(step))
            at = rng.randrange(len(oracle) + 1)
            book.insert(r, oracle[at]['id'] if at < len(oracle) else None, True)
            oracle.insert(at, r)
        elif operation == 'remove':
            i = rng.randrange(len(oracle))
            assert book.remove(oracle[i]['id']) == oracle.pop(i)
        elif operation == 'move':
            i = rng.randrange(len(oracle))
            r = oracle.pop(i)
            at = rng.randrange(len(oracle) + 1)
            book.move(r['id'], oracle[at]['id'] if at < len(oracle) else None, True)
            oracle.insert(at, r)
        else:
            i = rng.randrange(len(oracle))
            r = dict(oracle[i], notes=str(step))
            book.update(r['id'], r)
            oracle[i] = r
        assert book.validate()
        assert list(book) == oracle
        backward = []
        node = book.tail
        while node:
            backward.append(node.data)
            node = node.prev
        assert backward == oracle[::-1]


def test_linked_boundaries():
    b = LinkedBook()
    assert b.validate()
    a, c = record('A'), record('C')
    b.insert(a)
    b.move(a['id'], a['id'])
    with pytest.raises(KeyError):
        b.move(a['id'], 'absent')
    with pytest.raises(ValueError):
        b.insert(a)
    assert list(b) == [a]
    b.insert(c, a['id'])
    b.remove(a['id'])
    b.remove(c['id'])
    assert b.head is b.tail is None
    assert b.validate()


def test_restart_order_edit_delete_restore(store):
    a, b, c = record('同名'), record('同名'), record('C')
    store.save(a)
    store.save(b)
    store.save(c, b['id'], True)
    edited = dict(a, notes='修改', custom={'关系': '虚构'}, birth='2001')
    store.save(edited, expected=1)
    store.move(b['id'], a['id'], True)
    store.delete(c['id'])
    expected = copy.deepcopy(store.payload())
    store.reload()
    assert store.payload() == expected
    assert [r['id'] for r in store.book] == [b['id'], a['id']]
    store.restore_item(c['id'])
    assert store.book.tail.data['id'] == c['id']


@pytest.mark.parametrize('birth', ['', '2000', '2000-02', '0001'])
def test_partial_birth(birth):
    assert validate_record(record(birth=birth))['birth'] == birth


@pytest.mark.parametrize('birth', ['2000-00', '2000-13', '2000-1', '2000-01-01', '0000', '9999', 'hello'])
def test_invalid_birth(birth):
    with pytest.raises(ValueError):
        validate_record(record(birth=birth))


def test_stale_version_and_duplicate_submit(store):
    a = record()
    store.save(a)
    with pytest.raises(ValueError):
        store.save(a)
    store.save(dict(a, notes='new'), expected=1)
    with pytest.raises(ValueError):
        store.save(dict(a, notes='stale'), expected=1)
    assert store.book.get(a['id'])['notes'] == 'new'


def test_external_conflict(store):
    other = Store(store.path)
    try:
        store.save(record('first'))
        old = other.payload()
        with pytest.raises(ValueError, match='另一窗口'):
            other.save(record('second'))
        assert other.payload() == old
        other.reload()
        assert len(other.book) == 1
    finally:
        other.close()


def test_disk_write_failure_preserves_memory_and_disk(store):
    a = record()
    store.save(a)
    before = copy.deepcopy(store.payload())
    store.db.execute('PRAGMA query_only=ON')
    with pytest.raises(sqlite3.OperationalError):
        store.delete(a['id'])
    assert store.payload() == before
    store.db.execute('PRAGMA query_only=OFF')
    store.reload()
    assert store.payload() == before


def test_backup_recover_photo_custom_trash_order(store, tmp_path):
    img = io.BytesIO()
    Image.new('RGB', (20, 20), 'purple').save(img, 'PNG')
    a, b = record(photo=photo_bytes(img.getvalue()), custom={'虚构属性': '演示'}), record('B')
    store.save(a)
    store.save(b, a['id'], True)
    c = record('trash')
    store.save(c)
    store.delete(c['id'])
    before = copy.deepcopy(store.payload())
    archive = tmp_path / 'backup.json'
    store.export(archive, True)
    store.delete(a['id'])
    safety_state = copy.deepcopy(store.payload())
    safety = store.recover(archive)
    assert store.payload() == before
    assert json.loads(safety.read_text(encoding='utf-8')) == safety_state
    store.reload()
    assert store.payload() == before


def test_repeated_import_and_bad_import_atomic(store, tmp_path):
    a = record()
    path = tmp_path / 'import.json'
    atomic_json(path, dict(schema=1, active=[a], trash=[]))
    assert store.import_file(path) == (1, 0)
    assert store.import_file(path) == (0, 1)
    store.delete(a['id'])
    assert store.import_file(path) == (0, 1)
    before = copy.deepcopy(store.payload())
    bad = record(birth='bad')
    atomic_json(path, dict(schema=1, active=[record(), bad], trash=[]))
    with pytest.raises(ValueError):
        store.import_file(path)
    assert store.payload() == before
    with pytest.raises(ValueError):
        store.recover(path)
    assert store.payload() == before


def test_search_duplicates_and_merge(store):
    a = record('林可（虚构）', contacts={'手机': 'demo-123'}, tags=['徒步'], group='同学', favorite=True)
    b = record('林可（虚构）', notes='另一档案')
    store.save(a)
    store.save(b)
    assert list(store.search('林可 demo', '同学', '徒步', True)) == [a]
    assert list(store.duplicates(a)) == [b]
    store.merge(a['id'], b['id'], dict(a, notes=b['notes']), 1)
    assert len(store.book) == 1 and b['id'] in store.trash
    store.restore_item(b['id'])
    assert len(store.book) == 2


def test_invalid_image_and_db_path_protection(store):
    with pytest.raises(ValueError):
        photo_bytes(b'not an image')
    with pytest.raises(ValueError):
        store.save(record(photo='!!!!'))
    with pytest.raises(ValueError):
        store.export(store.path, True)


def test_large_chain_non_recursive_commit(store):
    def fill(book, trash):
        for i in range(1600):
            book.insert(record(str(i)))
    store.change(fill)
    store.save(record('last'))
    assert len(store.book) == 1601 and store.book.validate()


def test_corrupt_database_untouched(tmp_path):
    path = tmp_path / 'broken.sqlite3'
    path.write_bytes(b'NOT SQLITE: preserve me')
    with pytest.raises(sqlite3.DatabaseError):
        Store(path)
    assert path.read_bytes() == b'NOT SQLITE: preserve me'


def test_interrupted_sqlite_transaction(store):
    store.save(record())
    before = store.payload()
    other = sqlite3.connect(store.path)
    other.execute("UPDATE state SET payload='broken' WHERE id=1")
    other.close()  # 未提交事务模拟中断；SQLite 回滚
    store.reload()
    assert store.payload() == before
