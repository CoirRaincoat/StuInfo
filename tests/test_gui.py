import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
from datetime import date
from pathlib import Path
import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QComboBox, QInputDialog, QFileDialog
from PySide6.QtTest import QTest
from friendbook.core import Store, new_record
from friendbook.gui import Window
from friendbook.ui_widgets import Editor


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    store = Store(tmp_path / 'gui.sqlite3')
    a, b = new_record(), new_record()
    a.update(name='Z（虚构）', birth='2000', group='同学', custom={'测试属性': '保留'})
    b.update(name='A（虚构）', birth='', group='朋友')
    store.save(a)
    store.save(b)
    widget = Window(store)
    widget.resize(1280, 800)
    widget.show()
    app.processEvents()
    yield widget
    if widget._busy:
        wait_task(widget)
    widget.discard_editor()
    widget.close()
    app.processEvents()
    store.close()


def wait_task(window):
    until = time.monotonic() + 15
    while (window._busy or window._tasks) and time.monotonic() < until:
        QApplication.processEvents()
        QTest.qWait(5)
    assert not window._busy and not window._tasks, 'Worker did not finish'
    QApplication.processEvents()


def test_sorted_selection_and_filter_identity(window):
    ids = [r['id'] for r in window.store.records()]
    window.sort.setCurrentIndex(1)
    window.table.selectRow(0)
    assert window.selected() == ids[1]
    assert not window.up_button.isEnabled()
    assert [r['id'] for r in window.store.records()] == ids
    window.query.setText('Z')
    QTest.qWait(300)
    assert window.selected() is None
    window.table.selectRow(0)
    assert window.selected() == ids[0]
    assert window.before_button.isEnabled()
    window.edit()
    window.editor.fields['name'].setText('Z 修改')
    window.save_editor()
    wait_task(window)
    assert window.store.record(ids[0])['name'] == 'Z 修改'
    assert window.store.record(ids[1])['name'] == 'A（虚构）'


def test_inline_add_validation_and_duplicate_submit(window):
    window.add_button.click()
    assert window.editor and not window.editor.isWindow()
    uid = window.editor.original['id']
    window.editor.fields['birth'].setText('2000-13')
    window.save_editor()
    assert window.editor and window.editor.error.isVisible()
    assert window.store.counts()[0] == 2
    window.editor.fields['birth'].setText('2000')
    window.editor.fields['name'].setText('新增虚构')
    window.editor.custom.add('爱好细节', '长跑')
    window.editor.notes.setPlainText('新增备注')
    window.save_editor()
    assert window._busy and not window.workspace.isEnabled()
    window.save_editor()  # duplicate click cannot schedule a second command
    wait_task(window)
    assert window.editor is None
    assert window.selected() == uid
    assert window.store.counts()[0] == 3
    assert window.store.record(uid)['custom'] == {'爱好细节': '长跑'}


@pytest.mark.parametrize('target', ['selection', 'page', 'filter', 'close'])
def test_dirty_cancel_preserves_draft_and_selection(window, monkeypatch, target):
    window.table.selectRow(0)
    uid = window.selected()
    window.edit()
    window.editor.notes.setPlainText('尚未保存的草稿')
    monkeypatch.setattr(window, 'unsaved_choice', lambda: QMessageBox.StandardButton.Cancel)
    if target == 'selection':
        window.table.selectRow(1)
    elif target == 'page':
        window.nav.setCurrentRow(0)
    elif target == 'filter':
        window.sort.setCurrentIndex(1)
    else:
        window.close()
    assert window.editor.notes.toPlainText() == '尚未保存的草稿'
    assert window.selected() == uid
    assert window.table_uid() == uid
    assert window.page_name == '好友'
    assert window.isVisible()
    assert window.sort.currentIndex() == 0


def test_dirty_save_then_navigate_and_discard(window, monkeypatch):
    window.table.selectRow(0)
    uid = window.selected()
    window.edit()
    window.editor.notes.setPlainText('保存后切页')
    monkeypatch.setattr(window, 'unsaved_choice', lambda: QMessageBox.StandardButton.Save)
    window.navigate('概览')
    assert window.page_name == '好友'
    wait_task(window)
    assert window.page_name == '概览'
    assert window.store.record(uid)['notes'] == '保存后切页'
    window.open_friend(uid)
    window.edit()
    window.editor.notes.setPlainText('丢弃草稿')
    monkeypatch.setattr(window, 'unsaved_choice', lambda: QMessageBox.StandardButton.Discard)
    window.navigate('统计')
    assert window.editor is None and window.page_name == '统计'
    assert window.store.record(uid)['notes'] == '保存后切页'


def test_failed_async_save_preserves_input_and_blocks_navigation(window, monkeypatch):
    window.table.selectRow(0)
    uid = window.selected()
    window.edit()
    window.editor.notes.setPlainText('失败后保留输入')
    def fail(*args, **kwargs):
        raise OSError('injected write failure')
    monkeypatch.setattr(Store, 'save', fail)
    monkeypatch.setattr(window, 'unsaved_choice', lambda: QMessageBox.StandardButton.Save)
    window.navigate('概览')
    wait_task(window)
    assert window.editor.notes.toPlainText() == '失败后保留输入'
    assert '未保存' in window.editor.error.text()
    assert window.page_name == '好友'
    assert window.store.record(uid)['notes'] == ''
    assert window.workspace.isEnabled()


def test_delete_restore_purge_clear_stale_detail(window, monkeypatch):
    monkeypatch.setattr(window, 'confirm', lambda *args: True)
    window.table.selectRow(0)
    uid = window.selected()
    window.delete()
    wait_task(window)
    assert window.selected() is None
    window.navigate('回收站')
    window.select_uid(uid)
    window.edit()  # restore
    wait_task(window)
    assert window.selected() is None and window.table.rowCount() == 0
    window.navigate('好友')
    window.select_uid(uid)
    window.delete()
    wait_task(window)
    window.navigate('回收站')
    window.select_uid(uid)
    window.delete()
    wait_task(window)
    assert window.store.counts() == (1, 0)


def test_teaching_and_all_pages_and_themes(window):
    rows = window.store.connection_rows()
    for dark in (False, True):
        window.set_theme(dark)
        for page in window.PAGE_NAMES:
            window.navigate(page)
            QApplication.processEvents()
            assert window.page_name == page
            assert not window.grab().isNull()
    assert window.links_table.item(0, 0).text() == 'NULL ← HEAD'
    assert window.links_table.item(0, 3).text() == rows[0][3]


def test_compact_layout_and_long_content(window):
    window.resize(900, 650)
    QApplication.processEvents()
    assert window.list_area.isVisible() and not window.detail_panel.isVisible()
    window.table.selectRow(0)
    QApplication.processEvents()
    assert not window.list_area.isVisible() and window.detail_panel.isVisible()
    window.edit()
    window.editor.notes.setPlainText('虚构长备注\n' * 1000)
    window.editor.tabs.setCurrentIndex(3)
    assert window.editor.save_button.isVisible()
    window.discard_editor()
    window.back_to_list()
    assert window.list_area.isVisible()
    # Reopening the already selected row must work with one click as well.
    item = window.table.item(window.table.currentRow(), 0)
    QTest.mouseClick(window.table.viewport(), Qt.MouseButton.LeftButton,
                     pos=window.table.visualItemRect(item).center())
    assert window.detail_panel.isVisible() and not window.list_area.isVisible()
    window.resize(1280, 800)
    QApplication.processEvents()
    assert window.list_area.isVisible() and window.detail_panel.isVisible()


def test_merge_conflict_preview_then_explicit_inline_save(window, monkeypatch):
    records = window.store.records()
    a, b = records
    window.store.save(dict(b, name=a['name'], birth='2001'), expected=b['version'])
    window.refresh_all()
    window.select_uid(a['id'])
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args, **kwargs: (args[3][0], True))
    def choose(dialog):
        for combo in dialog.findChildren(QComboBox):
            combo.setCurrentIndex(1)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, 'exec', choose)
    window.merge()
    assert window.editor and window.store.counts()[0] == 2
    window.save_editor()
    wait_task(window)
    assert window.store.counts() == (1, 1)
    assert window.store.record(a['id'])['birth'] == '2001'
    assert window.store.record(b['id'], trash=True)['birth'] == '2001'


def test_import_backup_restore_through_ui(window, tmp_path, monkeypatch):
    archive = tmp_path / 'backup.json'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **k: (str(archive), ''))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **k: (str(archive), ''))
    monkeypatch.setattr(window, 'confirm', lambda *a: True)
    before = window.store.payload()
    window.backup()
    wait_task(window)
    assert archive.exists()
    window.import_data()
    wait_task(window)
    assert window.store.counts()[0] == 2
    window.store.delete(window.store.records()[0]['id'])
    window.refresh_all()
    window.recover()
    wait_task(window)
    assert window.store.payload() == before


def test_async_conflict_preserves_draft(window):
    window.table.selectRow(0)
    window.edit()
    window.editor.notes.setPlainText('等待保存')
    other = Store(window.store.path)
    other.save(new_record())
    other.close()
    window.save_editor()
    wait_task(window)
    assert window.editor and '其他窗口' in window.editor.error.text()
    assert window.store.counts()[0] == 2


def test_close_during_save_is_deferred(window, monkeypatch):
    original = Store.save
    def slow(self, *args, **kwargs):
        time.sleep(.15)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Store, 'save', slow)
    window.add()
    window.save_editor()
    window.close()
    assert window.isVisible()
    wait_task(window)
    assert window.store.counts()[0] == 3


def test_sorted_insert_uses_anchor_in_original_order(window):
    original = [r['id'] for r in window.store.records()]
    window.sort.setCurrentIndex(1)
    window.table.selectRow(0)
    assert window.selected() == original[1]
    window.before_button.trigger()
    uid = window.editor.original['id']
    window.editor.fields['name'].setText('插入演示')
    window.save_editor()
    wait_task(window)
    assert [r['id'] for r in window.store.records()] == [original[0], uid, original[1]]
    assert window.sort.currentIndex() == 1


def test_group_page_rename_dissolve_and_navigation(window, monkeypatch):
    window.navigate('分组')
    window.groups_table.selectRow(0)
    old = window.selected_group()
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **k: ('重命名分组', True))
    window.rename_selected_group()
    wait_task(window)
    assert '重命名分组' in window.store.group_counts()
    assert old not in window.store.group_counts()
    row = next(i for i in range(window.groups_table.rowCount()) if window.groups_table.item(i, 0).text() == '重命名分组')
    window.groups_table.selectRow(row)
    window.open_selected_group()
    assert window.page_name == '好友' and window.table.rowCount() == 1
    assert window._filters[1] == '重命名分组'
    window.navigate('分组')
    window.groups_table.selectRow(row)
    monkeypatch.setattr(window, 'confirm', lambda *a: True)
    window.dissolve_selected_group()
    wait_task(window)
    assert '重命名分组' not in window.store.group_counts()
    assert window.store.counts()[0] == 2


def test_save_then_close_and_long_record_layout(window, monkeypatch):
    record = window.store.records()[0]
    window.store.save(dict(record, name='长姓名' * 80, notes='longword' * 1000,
                           custom={'很长的属性名' * 20: '属性值' * 300}), expected=record['version'])
    window.refresh_all()
    window.resize(900, 650)
    window.select_uid(record['id'])
    QApplication.processEvents()
    assert window.width() == 900
    window.edit()
    window.editor.notes.setPlainText('保存后关闭')
    monkeypatch.setattr(window, 'unsaved_choice', lambda: QMessageBox.StandardButton.Save)
    window.close()
    wait_task(window)
    assert not window.isVisible()
    assert window.store.record(record['id'])['notes'] == '保存后关闭'
