"""Overview drill-down and the first-entry chart motion."""
from datetime import date
from PySide6.QtCore import Qt, QAbstractAnimation
from PySide6.QtWidgets import QApplication, QTableWidget, QInputDialog
from PySide6.QtTest import QTest
from friendbook.core import new_record
from friendbook.labels import with_labels
from friendbook.ui_charts import ChartCanvas
from test_gui import app, window, wait_until, wait_task


def test_overview_cards_show_all_monthly_birthdays_and_favorites(window):
    birthday_ids = []
    favorite_ids = []
    for index in range(8):
        record = new_record()
        record.update(name=f'本月好友 {index}', birth=f'2000-{date.today().month:02}', favorite=index < 3)
        window.store.save(record)
        birthday_ids.append(record['id'])
        if record['favorite']:
            favorite_ids.append(record['id'])
    deleted = new_record()
    deleted.update(name='回收站好友', birth=f'2000-{date.today().month:02}', favorite=True)
    window.store.save(deleted)
    window.store.delete(deleted['id'])
    window.navigate('概览')
    window.home_birthdays_card.click()
    QApplication.processEvents()
    dialog = window.collection_dialog
    table = dialog.findChild(QTableWidget, 'overviewCollection')
    assert table.rowCount() == 8
    assert [table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in range(8)] == birthday_ids
    # The last result is reachable even when the overview preview only shows six.
    table.scrollToItem(table.item(7, 0))
    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton,
                    pos=table.visualItemRect(table.item(7, 0)).center())
    assert window.page_name == '好友' and window.selected() == birthday_ids[-1]
    window.navigate('概览')
    window.home_favorites_card.click()
    QApplication.processEvents()
    table = window.collection_dialog.findChild(QTableWidget, 'overviewCollection')
    assert [table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in range(table.rowCount())] == favorite_ids
    window.collection_dialog.close()


def test_empty_collection_and_creating_unused_label(window, monkeypatch):
    window.navigate('概览')
    window.home_favorites_card.click()
    assert window.collection_dialog.findChild(QTableWidget).rowCount() == 0
    window.collection_dialog.close()
    window.navigate('分组')
    monkeypatch.setattr(QInputDialog, 'getText', lambda *args, **kwargs: ('尚未使用', True))
    window.add_group()
    wait_task(window)
    assert '尚未使用' in window.store.label_names()
    row = next(row for row in range(window.groups_table.rowCount())
               if window.groups_table.item(row, 0).text() == '尚未使用')
    assert window.groups_table.item(row, 1).text() == '0'


def test_multi_label_statistics_counts_every_label(window):
    uid = window.store.records()[0]['id']
    record = window.store.record(uid)
    window.store.save(with_labels(record, ['同学', '跑友']), expected=record['version'])
    window.store.create_label('待认识')
    window.set_reduce_motion(True)
    window.navigate('统计')
    QApplication.processEvents()
    chart = window.stats_charts['标签']
    assert dict(chart.counts) == {'同学': 1, '跑友': 1, '朋友': 1, '待认识': 0}
    assert chart.canvas.progress == 1.
    chart.choice.setCurrentIndex(1)
    assert chart.canvas.mode == 'donut' and chart.canvas.progress == 1.
    assert sum(span for _, _, span in chart.canvas.donut_spans()) == 360.
    assert chart.animation.state() == QAbstractAnimation.State.Stopped
    assert set(window.stats_charts) == {'标签', '年龄', '兴趣', '生日月份'}


def test_charts_animate_only_first_view_of_each_mode(window):
    window.set_reduce_motion(False)
    window.navigate('统计')
    QApplication.processEvents()
    chart = window.stats_charts['标签']
    assert chart.animation.state() == QAbstractAnimation.State.Running
    assert chart.canvas.progress < 1.
    wait_until(lambda: chart.canvas.progress == 1., 'Initial bars did not finish growing')
    chart.choice.setCurrentIndex(1)
    assert chart.canvas.progress < 1.
    wait_until(lambda: chart.canvas.progress == 1., 'Initial donut did not finish sweeping')
    chart.choice.setCurrentIndex(0)
    assert chart.canvas.progress == 1.
    assert chart.animation.state() == QAbstractAnimation.State.Stopped
    window.navigate('好友')
    window.navigate('统计')
    QApplication.processEvents()
    rebuilt = window.stats_charts['标签']
    assert rebuilt.canvas.progress == 1.
    assert rebuilt.animation.state() == QAbstractAnimation.State.Stopped


def test_chart_growth_is_bottom_anchored_and_donut_sweeps_clockwise(app):
    canvas = ChartCanvas([('标签一', 1), ('标签二', 3), ('空标签', 0)])
    canvas.resize(480, 360)
    canvas.progress = .25
    partial = [rect for _, _, rect in canvas.bar_rects()]
    canvas.progress = 1.
    complete = [rect for _, _, rect in canvas.bar_rects()]
    assert all(a.bottom() == b.bottom() for a, b in zip(partial, complete))
    assert all(a.height() == b.height() / 4 for a, b in zip(partial, complete))
    canvas.progress = .125
    spans = canvas.donut_spans()
    assert spans[0] == (0, 0., 45.)
    assert spans[1][2] == 0.
    canvas.progress = .5
    assert canvas.donut_spans()[:2] == [(0, 0., 90.), (1, 90., 90.)]
    canvas.deleteLater()
