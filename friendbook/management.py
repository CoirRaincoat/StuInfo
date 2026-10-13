"""A management draft owns a separate linked snapshot and never opens SQLite."""
import json
import copy

from . import core
from .core import Store
from .labels import normalize_labels, record_labels
from .linked import LinkedBook


def clone_state(store):
    """Clone trusted in-memory state; external archives still go through decode."""
    book = LinkedBook()
    for record in store.book:
        book.insert(copy.deepcopy(record))
    return book, copy.deepcopy(store.trash)


class ManagementSession(Store):
    def __init__(self, store):
        self.path = store.path
        self.base_revision = self.revision = store.revision
        self.book, self.trash = clone_state(store)
        self.label_catalog = list(store.label_catalog)
        self._original = self.payload()

    @classmethod
    def from_payload(cls, store, payload):
        draft = cls(store)
        draft.book, draft.trash = draft.decode(payload)
        draft.label_catalog = draft._catalog_from_payload(payload)
        return draft

    @property
    def dirty(self):
        # Compare with the immutable baseline without copying every record on each click.
        original = self._original
        if (self.label_catalog != original['label_catalog'] or
                len(self.book) != len(original['active']) or
                len(self.trash) != len(original['trash'])):
            return True
        return (any(record != old for record, old in zip(self.book, original['active'])) or
                any(record != old for record, old in zip(self.trash.values(), original['trash'])))

    def change(self, operation, *, label_catalog=None):
        # Use the same clone / validate / publish boundary as Store, without I/O.
        book, trash = clone_state(self)
        result = operation(book, trash)
        book.validate()
        catalog = normalize_labels(self.label_catalog if label_catalog is None else label_catalog, limit=50000)
        catalog = normalize_labels(list(dict.fromkeys(catalog + [label for record in book
                                                                 for label in record_labels(record)])), limit=50000)
        payload = dict(schema=1, active=list(book), trash=list(trash.values()), label_catalog=catalog)
        if len(book) > 50000 or len(trash) > 50000 or len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > core.MAX_FILE:
            raise ValueError('档案超过容量限制，本次管理操作未应用')
        self.book, self.trash, self.label_catalog = book, trash, catalog
        return result

    def close(self):
        pass
