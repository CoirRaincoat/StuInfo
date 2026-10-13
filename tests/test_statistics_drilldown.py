from datetime import date
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QFileDialog
from friendbook.core import new_record
from friendbook.labels import with_labels
from test_gui import app, window, wait_task


def test_statistics_click_maps_index_not_display_text(window):
    record = new_record()
    window.store.save(record)
    other = with_labels(new_record(), ['（未标记）'])
    window.store.save(other)
    window.navigate('统计')
    chart = window.stats_charts['标签']
    index = next(i for i, (name, _) in enumerate(chart.counts) if name == '（未标记）')
    chart.category_activated.emit(index)
    table = window.collection_dialog.findChild(QTableWidget)
    assert table.rowCount() == 1
    assert table.item(0, 0).data(Qt.ItemDataRole.UserRole) == other['id']
    window.collection_dialog.close()
    index = next(i for i, (name, _) in enumerate(chart.counts) if name.startswith('（未标记） ·'))
    chart.category_activated.emit(index)
    table = window.collection_dialog.findChild(QTableWidget)
    assert table.item(0, 0).data(Qt.ItemDataRole.UserRole) == record['id']
    table.cellClicked.emit(0, 0)
    assert window.page_name == '好友' and window.selected() == record['id']


def test_quality_drilldown_can_edit_and_refresh(window):
    window.open_quality_statistics()
    assert window.stats_tabs.tabText(window.stats_tabs.currentIndex()) == '资料检查'
    chart = window.stats_charts['资料检查']
    index = next(i for i, (name, _) in enumerate(chart.counts) if name == '出生年份未知')
    assert chart.counts[index][1] == 1
    chart.category_activated.emit(index)
    table = window.collection_dialog.findChild(QTableWidget)
    uid = table.item(0, 0).data(Qt.ItemDataRole.UserRole)
    table.cellClicked.emit(0, 0)
    window.edit()
    window.editor.fields['birth'].setText('2001')
    window.save_editor()
    wait_task(window)
    window.navigate('统计')
    assert dict(window.stats_charts['资料检查'].counts)['出生年份未知'] == 0
    assert window.store.record(uid)['birth'] == '2001'


def test_export_statistics_has_failure_feedback_and_protects_database(window, monkeypatch, tmp_path):
    window.navigate('统计')
    chart = window.stats_charts['标签']
    original = window.store.path.read_bytes()
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **k: (str(window.store.path), 'PNG'))
    window.export_statistics_chart(chart, '标签', '测试口径', 2, date.today())
    assert window.store.path.read_bytes() == original
    assert window.notice.objectName() == 'error'
    target = tmp_path / 'chart.png'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **k: (str(target), 'PNG'))
    window.export_statistics_chart(chart, '标签', '测试口径', 2, date.today())
    assert target.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
