import copy
import json
import os
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QAbstractAnimation, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from friendbook.core import Store, new_record
from friendbook.gui import Window
from friendbook.labels import record_labels


@pytest.fixture(scope='session')
def management_app():
    return QApplication.instance() or QApplication([])


def wait_until(predicate):
    until = time.monotonic() + 15
    while not predicate() and time.monotonic() < until:
        QTest.qWait(10)
    assert predicate(), 'Qt operation did not finish'


def wait_task(window):
    wait_until(lambda: not window._busy and not window._tasks)
    QApplication.processEvents()


@pytest.fixture
def managed_window(management_app, tmp_path):
    store = Store(tmp_path / 'management.sqlite3')
    for index in range(3):
        store.save(dict(new_record(), name=f'好友 {index}', group='原标签'))
    widget = Window(store)
    widget.resize(1280, 800)
    widget.set_reduce_motion(True)
    widget.show()
    QApplication.processEvents()
    yield widget
    if widget._busy:
        wait_task(widget)
    if widget.managing:
        widget.set_management(False)
    widget.discard_editor()
    widget.close()
    widget.deleteLater()
    management_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    management_app.processEvents()
    store.close()


def stage_changes(window, monkeypatch):
    ids = [record['id'] for record in window.store.records()]
    window.management_button.click()
    window.toggle_friend_check(ids[0])
    window.apply_batch('favorite', True)
    window.apply_batch('labels', ['同学', '旅行'])
    window.reorder_friends([ids[0]], None)
    window.toggle_friend_check(ids[0])
    window.toggle_friend_check(ids[1])
    monkeypatch.setattr(window, 'confirm', lambda *_: True)
    window.apply_batch('delete')
    return ids


def test_management_cancel_discards_all_staged_operations(managed_window, monkeypatch):
    window = managed_window
    original = copy.deepcopy(window.store.payload())
    revision = window.store.revision
    ids = stage_changes(window, monkeypatch)
    assert window.management_button.isVisible()
    assert window.management_button.text() == '取消'
    assert [record['id'] for record in window.friend_source().records()] == [ids[2], ids[0]]
    assert window.friend_source().record(ids[0])['favorite']
    assert record_labels(window.friend_source().record(ids[0])) == ['同学', '旅行']
    assert window.friend_source().counts() == (2, 1)
    assert window.store.payload() == original
    assert window.store.revision == revision
    monkeypatch.setattr(window, 'confirm_cancel_management', lambda: True)
    window.management_button.click()
    assert not window.managing and window._management_session is None
    assert window.management_button.isVisible()
    assert window.table.columnCount() == 4
    window.store.reload()
    assert window.store.payload() == original
    assert window.store.revision == revision


def test_management_done_commits_whole_session_once(managed_window, monkeypatch):
    window = managed_window
    revision = window.store.revision
    ids = stage_changes(window, monkeypatch)
    window.management_done_button.click()
    wait_task(window)
    assert not window.managing
    assert window.store.revision == revision + 1
    window.store.reload()
    assert [record['id'] for record in window.store.records()] == [ids[2], ids[0]]
    assert window.store.record(ids[0])['favorite']
    assert record_labels(window.store.record(ids[0])) == ['同学', '旅行']
    assert window.store.counts() == (2, 1)
    assert window.store.record(ids[1], trash=True)['name'] == '好友 1'


def test_management_failed_commit_keeps_preview_and_can_retry(managed_window, monkeypatch):
    window = managed_window
    original = copy.deepcopy(window.store.payload())
    uid = window.store.records()[0]['id']
    window.management_button.click()
    window.toggle_friend_check(uid)
    window.apply_batch('favorite', True)
    candidate = window._management_session.payload()
    commit = Store.commit_management
    def fail(*_):
        raise OSError('injected commit failure')
    monkeypatch.setattr(Store, 'commit_management', fail)
    window.management_done_button.click()
    wait_task(window)
    assert window.managing
    assert window._management_session.payload() == candidate
    assert window.selected_batch_ids() == [uid]
    assert window.store.payload() == original
    assert window.workspace.isEnabled()
    monkeypatch.setattr(Store, 'commit_management', commit)
    window.management_done_button.click()
    wait_task(window)
    assert not window.managing and window.store.record(uid)['favorite']


def test_management_cancel_warning_remembers_only_confirmed_choice(managed_window, monkeypatch):
    window = managed_window
    window.management_button.click()
    def decline(box):
        assert box.checkBox().text() == '知道，以后不再提示'
        box.checkBox().setChecked(True)
        return QMessageBox.StandardButton.Cancel
    monkeypatch.setattr(QMessageBox, 'exec', decline)
    window.management_button.click()
    assert window.managing
    assert not window.settings.value('skip_management_cancel_warning', False, bool)
    def discard(box):
        box.checkBox().setChecked(True)
        return QMessageBox.StandardButton.Discard
    monkeypatch.setattr(QMessageBox, 'exec', discard)
    window.management_button.click()
    assert not window.managing
    window.settings.sync()
    assert window.settings.value('skip_management_cancel_warning', False, bool)
    def unexpected(_):
        pytest.fail('Remembered cancel preference should suppress the warning')
    monkeypatch.setattr(QMessageBox, 'exec', unexpected)
    window.management_button.click()
    window.management_button.click()
    assert not window.managing


@pytest.mark.parametrize('decision', ['Cancel', 'Discard', 'Save'])
def test_management_navigation_guard_respects_all_choices(managed_window, monkeypatch, decision):
    window = managed_window
    uid = window.store.records()[0]['id']
    window.management_button.click()
    window.toggle_friend_check(uid)
    window.apply_batch('favorite', True)
    monkeypatch.setattr(window, 'management_leave_choice',
                        lambda: getattr(QMessageBox.StandardButton, decision))
    continued = []
    window.request_leave_management(lambda: continued.append(True))
    wait_task(window)
    assert window.managing == (decision == 'Cancel')
    assert continued == ([] if decision == 'Cancel' else [True])
    assert window.store.record(uid)['favorite'] == (decision == 'Save')


def test_management_export_uses_preview_without_committing(managed_window, monkeypatch, tmp_path):
    window = managed_window
    uid = window.store.records()[0]['id']
    revision = window.store.revision
    window.management_button.click()
    window.toggle_friend_check(uid)
    window.apply_batch('favorite', True)
    path = tmp_path / 'selection.json'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *_: (str(path), ''))
    window.batch_export()
    wait_task(window)
    exported = json.loads(path.read_text(encoding='utf-8'))
    assert len(exported['active']) == 1
    assert exported['active'][0]['id'] == uid and exported['active'][0]['favorite']
    assert window.managing and window._management_session.dirty
    assert not window.store.record(uid)['favorite']
    assert window.store.revision == revision


def test_management_toolbar_animates_height_and_respects_reduce_motion(managed_window):
    window = managed_window
    window.set_reduce_motion(False)
    QApplication.processEvents()
    original_top = window.splitter.y()
    window.management_button.click()
    assert window.management_bar.animation.state() == QAbstractAnimation.State.Running
    wait_until(lambda: window.management_bar.maximumHeight() > 0)
    assert window.management_bar.isVisible()
    wait_until(lambda: window.management_bar.animation.state() == QAbstractAnimation.State.Stopped)
    QApplication.processEvents()
    assert window.splitter.y() > original_top
    window.set_reduce_motion(True)
    window.set_management(False)
    QApplication.processEvents()
    assert window.management_bar.animation.state() == QAbstractAnimation.State.Stopped
    assert not window.management_bar.isVisible()
    assert window.splitter.y() == original_top
