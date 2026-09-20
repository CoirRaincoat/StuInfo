"""Long-running persistence work uses its own SQLite connection, never Qt widgets."""
from PySide6.QtCore import QThread, Signal
from .core import Store


class StoreTask(QThread):
    completed = Signal(object)
    failed = Signal(object)

    def __init__(self, path, revision, method, args=(), kwargs=None, parent=None):
        super().__init__(parent)
        self.path, self.revision, self.method = path, revision, method
        self.args, self.kwargs = args, kwargs or {}

    def run(self):
        store = None
        try:
            store = Store(self.path)
            if self.method != 'reload' and store.revision != self.revision:
                raise ValueError('数据已被其他窗口修改。请先在设置中刷新，再重新打开档案。草稿已保留。')
            result = getattr(store, self.method)(*self.args, **self.kwargs)
            snapshot = (result, store.book, store.trash, store.revision)
            store.close()
            store = None
            self.completed.emit(snapshot)
        except Exception as exc:
            self.failed.emit(exc)
        finally:
            if store:
                store.close()
