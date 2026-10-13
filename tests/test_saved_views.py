import json
import os
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QEvent, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from friendbook.core import Store, new_record
from friendbook.gui import Window
from friendbook.ui_saved_views import decode_views, SETTINGS_KEY


@pytest.fixture
def view_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / 'views.sqlite3')
    store.save(dict(new_record(), name='甲（虚构）', interests='阅读', group='同学'))
    store.save(dict(new_record(), name='乙（虚构）', interests='摄影', favorite=True))
    window = Window(store)
    window.set_reduce_motion(True)
    window.resize(900, 650)
    window.show()
    app.processEvents()
    yield window
    wait_worker(window)
    window.discard_editor()
    window.set_management(False)
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    store.close()


def wait_worker(window):
    until = time.monotonic() + 10
    while (window._busy or window._tasks) and time.monotonic() < until:
        QTest.qWait(10)
    assert not window._busy and not window._tasks


def save_view(window, monkeypatch, name='我的视图'):
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **k: (name, True))
    window.save_current_view()


def test_save_captures_pending_query_and_restarts_without_changing_records(view_window, monkeypatch):
    window = view_window
    before = window.store.payload()
    revision = window.store.revision
    window.query.setText('阅读')
    assert window.search_timer.isActive() and window._filters[0] == ''
    save_view(window, monkeypatch, '读书好友')
    assert window._filters == ('阅读', None, '', False, 0)
    assert window._saved_views == [{'name': '读书好友', 'filters': ['阅读', None, '', False, 0]}]
    assert len(window._visible_records) == 1
    assert not window.search_timer.isActive()
    assert window.store.payload() == before and window.store.revision == revision
    other = Window(window.store)
    assert other._saved_views == window._saved_views
    other.close()
    other.deleteLater()


def test_update_duplicate_and_delete_need_confirmation(view_window, monkeypatch):
    window = view_window
    save_view(window, monkeypatch)
    original = list(window._saved_views)
    window.set_filters(('摄影', None, '', True, 1))
    monkeypatch.setattr(window, 'confirm', lambda *a: False)
    save_view(window, monkeypatch)
    window.update_saved_view()
    window.delete_saved_view()
    assert window._saved_views == original
    monkeypatch.setattr(window, 'confirm', lambda *a: True)
    window.update_saved_view()
    assert tuple(window._saved_views[0]['filters']) == window._filters
    current_filters = window._filters
    window.delete_saved_view()
    assert not window._saved_views and window._filters == current_filters
    assert not window.apply_view_button.isEnabled()


@pytest.mark.parametrize('decision', [QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Discard,
                                     QMessageBox.StandardButton.Save])
def test_apply_view_guards_dirty_editor_by_stable_id(view_window, monkeypatch, decision):
    window = view_window
    ids = [record['id'] for record in window.store.records()]
    window.set_filters(('摄影', None, '', False, 1))
    save_view(window, monkeypatch)
    window.set_filters(('', None, '', False, 0))
    window.select_uid(ids[0])
    window.edit()
    window.editor.fields['name'].setText('甲修改（虚构）')
    monkeypatch.setattr(window, 'unsaved_choice', lambda: decision)
    window.apply_saved_view()
    wait_worker(window)
    if decision == QMessageBox.StandardButton.Cancel:
        assert window.editor and window.selected() == ids[0]
        assert window._filters[0] == ''
    else:
        assert window.editor is None and window._filters[0] == '摄影'
        assert [record['id'] for record in window._visible_records] == [ids[1]]
    assert window.store.record(ids[0])['name'] == ('甲修改（虚构）' if decision == QMessageBox.StandardButton.Save else '甲（虚构）')
    assert [record['id'] for record in window.store.records()] == ids


def test_view_switch_preserves_management_draft_and_resets_selection(view_window, monkeypatch):
    window = view_window
    window.set_filters(('摄影', None, '', False, 0))
    save_view(window, monkeypatch)
    window.set_filters(('', None, '', False, 0))
    window.set_management(True)
    uid = window._visible_records[0]['id']
    window.toggle_friend_check(uid)
    window.apply_batch('favorite', True)
    session = window._management_session
    assert session.dirty and session.record(uid)['favorite']
    window.apply_saved_view()
    assert window._management_session is session and session.dirty
    assert not window._checked_ids and window._filters[0] == '摄影'
    assert not window.store.record(uid)['favorite']


def test_invalid_settings_and_write_failure_do_not_change_records(view_window, monkeypatch):
    window = view_window
    before = window.store.payload()
    window.settings.setValue(SETTINGS_KEY, '{broken')
    window.settings.sync()
    other = Window(window.store)
    assert other._saved_views == []
    assert '无法读取' in other.notice.text()
    other.close()
    other.deleteLater()
    settings = window.settings
    class FailedSettings:
        def value(self, *args):
            return settings.value(*args)
        def setValue(self, *args):
            pass
        def sync(self):
            pass
        def status(self):
            return QSettings.Status.AccessError
    monkeypatch.setattr(window, 'settings', FailedSettings())
    save_view(window, monkeypatch)
    assert not window._saved_views
    assert '未保存' in window.notice.text()
    assert window.store.payload() == before
    monkeypatch.setattr(window, 'settings', settings)


def test_views_hidden_in_trash_and_fit_compact_filter_row(view_window):
    window = view_window
    window.filters_widget.show()
    QApplication.processEvents()
    assert window.saved_views_row.isVisible()
    assert window.saved_views_row.width() <= window.filters_widget.width()
    window.navigate('回收站')
    assert not window.saved_views_row.isVisible()
    window.save_current_view()
    assert not window._saved_views


@pytest.mark.parametrize('values', [None, {}, [{'name': ' ', 'filters': ['', None, '', False, 0]}],
    [{'name': 'a', 'filters': ['', None, '', False, True]}],
    [{'name': 'a', 'filters': ['', None, '', False, 3]}],
    [{'name': 'a', 'filters': ['x' * 1001, None, '', False, 0]}],
    [{'name': 'a', 'filters': ['', None, '', 1, 0]}],
    [{'name': 'a', 'filters': ['', None, '', False, 0]}] * 2,
    [{'name': str(i), 'filters': ['', None, '', False, 0]} for i in range(21)]])
def test_saved_view_json_validation(values):
    with pytest.raises(ValueError):
        decode_views(json.dumps(values))
