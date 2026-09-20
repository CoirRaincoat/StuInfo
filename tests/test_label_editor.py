"""UI round trips for the label picker and detail-level favorite action."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QCheckBox, QLabel, QStyleOptionViewItem, QStyle
from friendbook.core import Store
from friendbook.labels import record_labels
from test_gui import app, window, wait_task


def test_search_create_select_labels_preserves_both_remarks(window):
    record = window.store.records()[0]
    record.update(tags=['原有短备注'], notes='原有详细备注')
    window.store.save(record, expected=record['version'])
    window.refresh_all()
    window.select_uid(record['id'])
    window.edit()
    editor = window.editor
    assert 'group' not in editor.fields
    assert not editor.findChildren(QCheckBox)
    assert '备注' in [item.text() for item in editor.findChildren(QLabel)]
    picker = editor.label_picker
    picker.toggle.click()
    assert picker.panel.isVisible()
    picker.search.setText('朋')
    assert picker.options.count() == 1 and picker.options.item(0).text() == '朋友'
    picker.options.item(0).setCheckState(Qt.CheckState.Checked)
    picker.search.setText('新建测试标签')
    picker.create_button.click()
    assert record_labels(window.store.record(record['id'])) == ['同学']
    window.save_editor()
    wait_task(window)
    saved = window.store.record(record['id'])
    assert record_labels(saved) == ['同学', '朋友', '新建测试标签']
    assert saved['tags'] == ['原有短备注'] and saved['notes'] == '原有详细备注'
    window.edit()
    assert not window.editor.dirty()
    assert window.editor.label_picker.selected_labels() == record_labels(saved)
    other = Store(window.store.path)
    try:
        assert record_labels(other.record(record['id'])) == record_labels(saved)
        assert '新建测试标签' in other.label_names()
    finally:
        other.close()


def test_discard_new_label_does_not_create_catalog_entry(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    window.table.selectRow(0)
    window.edit()
    picker = window.editor.label_picker
    picker.search.setText('未保存标签')
    picker.create_label()
    monkeypatch.setattr(window, 'unsaved_choice', lambda: QMessageBox.StandardButton.Discard)
    window.navigate('分组')
    assert '未保存标签' not in window.store.label_names()


def test_favorite_star_is_persisted_and_failed_change_restores_state(window, monkeypatch):
    window.table.selectRow(0)
    uid = window.selected()
    assert window.favorite_button.text() == '☆'
    window.favorite_button.click()
    wait_task(window)
    assert window.store.record(uid)['favorite']
    assert window.favorite_button.text() == '★' and window.favorite_button.isChecked()
    other = Store(window.store.path)
    try:
        assert other.record(uid)['favorite']
    finally:
        other.close()
    def fail(*args, **kwargs):
        raise OSError('injected write failure')
    monkeypatch.setattr(Store, 'save', fail)
    window.favorite_button.click()
    wait_task(window)
    assert window.store.record(uid)['favorite']
    assert window.favorite_button.text() == '★' and window.favorite_button.isChecked()


def test_group_cell_focus_does_not_change_row_paint(window):
    window.navigate('分组')
    table = window.groups_table
    index = table.model().index(0, 0)
    def painted(focus):
        image = QImage(260, 48, QImage.Format.Format_ARGB32)
        image.fill(table.palette().base().color())
        painter = QPainter(image)
        option = QStyleOptionViewItem()
        option.initFrom(table)
        option.rect = QRect(0, 0, 260, 48)
        option.state |= QStyle.StateFlag.State_Selected
        if focus:
            option.state |= QStyle.StateFlag.State_HasFocus
        else:
            option.state &= ~QStyle.StateFlag.State_HasFocus
        table.itemDelegate().paint(painter, option, index)
        painter.end()
        return image
    assert painted(True) == painted(False)
