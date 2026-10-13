import pytest
from friendbook import core
from friendbook.core import Store, new_record
from friendbook.management import ManagementSession


def test_trusted_draft_changes_do_not_redecode_images(tmp_path, monkeypatch):
    store = Store(tmp_path / 'book.sqlite3')
    for name in ('虚构一', '虚构二', '虚构三'):
        record = new_record()
        record['name'] = name
        store.save(record)
    before = store.payload()
    # Any full archive decode/record revalidation would reach this function.
    def reject_revalidation(*args, **kwargs):
        raise AssertionError('A trusted drag/batch draft must not revalidate every photo')
    monkeypatch.setattr(core, 'validate_record', reject_revalidation)
    draft = ManagementSession(store)
    assert not draft.dirty
    ids = [r['id'] for r in draft.records()]
    draft.move_many([ids[2]], ids[0])
    assert draft.dirty
    draft.batch_update([ids[0]], 'favorite', True)
    assert draft.record(ids[0])['favorite']
    assert store.payload() == before
    # Reading dirty must not allocate another full snapshot.
    monkeypatch.setattr(draft, 'payload', reject_revalidation)
    assert draft.dirty
    store.close()


def test_draft_exception_discards_candidate_and_external_payload_is_validated(tmp_path):
    store = Store(tmp_path / 'book.sqlite3')
    record = new_record()
    store.save(record)
    draft = ManagementSession(store)
    before = draft.payload()
    def failing(book, trash):
        book.remove(record['id'])
        raise ValueError('injected failure')
    with pytest.raises(ValueError):
        draft.change(failing)
    assert draft.payload() == before and not draft.dirty
    invalid = draft.payload()
    invalid['active'][0]['photo'] = 'not-an-image'
    with pytest.raises(ValueError):
        ManagementSession.from_payload(store, invalid)
    assert store.payload() == before
    store.close()
