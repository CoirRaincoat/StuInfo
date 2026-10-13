"""Statistical category identity, accessible input and non-destructive chart export."""
import pytest
from PySide6.QtCore import Qt, QPoint, QPointF, QAbstractAnimation
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout

from friendbook.ui_charts import ChartCanvas, DistributionChart
from test_gui import app, wait_until


@pytest.fixture
def chart(app):
    widget = DistributionChart([('同名分类', 1), ('同名分类', 3), ('零值分类', 0)], '演示', set())
    widget.setProperty('reduceMotion', True)
    widget.resize(1000, 480)
    widget.show()
    QApplication.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    QApplication.processEvents()


def test_chart_hover_links_legend_and_reports_real_denominator(chart):
    rect = chart.canvas.bar_rects()[1][2]
    QTest.mouseMove(chart.canvas, rect.center().toPoint())
    assert chart.canvas.hover_index == chart.legend.hover_index == 1
    assert '3' in chart.summary.text() and '75.0%' in chart.summary.text()
    assert '统计归属次数' in chart.summary.text()
    assert chart.canvas.hover_animation.state() == QAbstractAnimation.State.Stopped
    assert chart.canvas.hover_progress == 1.
    QTest.mouseMove(chart.canvas, QPoint(3, 3))
    assert chart.canvas.hover_index == chart.legend.hover_index == -1


def test_click_emits_category_index_even_when_labels_collide_or_count_zero(chart):
    events = []
    chart.category_activated.connect(events.append)
    QTest.mouseClick(chart.canvas, Qt.MouseButton.LeftButton,
                     pos=chart.canvas.bar_rects()[1][2].center().toPoint())
    QTest.mouseClick(chart.legend, Qt.MouseButton.LeftButton, pos=QPoint(30, 78))
    assert events == [1, 2]
    assert chart.canvas.selected_index == chart.legend.selected_index == 2
    assert '0.0%' in chart.summary.text()


def test_keyboard_selection_activation_and_escape(chart):
    events = []
    chart.category_activated.connect(events.append)
    chart.legend.setFocus()
    QTest.keyClick(chart.legend, Qt.Key.Key_End)
    assert chart.canvas.selected_index == chart.legend.selected_index == 2
    QTest.keyClick(chart.legend, Qt.Key.Key_Return)
    assert events == [2]
    QTest.keyClick(chart.legend, Qt.Key.Key_Escape)
    assert chart.canvas.selected_index == chart.legend.selected_index == -1
    assert chart.canvas.hover_index == chart.legend.hover_index == -1


def test_click_release_outside_category_does_not_activate(chart):
    events = []
    chart.category_activated.connect(events.append)
    QTest.mousePress(chart.canvas, Qt.MouseButton.LeftButton,
                     pos=chart.canvas.bar_rects()[0][2].center().toPoint())
    QTest.mouseRelease(chart.canvas, Qt.MouseButton.LeftButton, pos=QPoint(1, 1))
    assert events == []


def test_ring_hit_testing_uses_visible_clockwise_arc_and_excludes_hole(app):
    canvas = ChartCanvas([('一', 1), ('二', 3), ('零', 0)])
    canvas.resize(480, 360)
    canvas.set_mode('donut')
    outer, ring, _ = canvas.donut_geometry()
    center = outer.center()
    r = ring.width() / 2 / 2 ** .5
    assert canvas.index_at(QPointF(center.x() + r, center.y() - r)) == 0
    assert canvas.index_at(QPointF(center.x() + r, center.y() + r)) == 1
    assert canvas.index_at(center) == -1
    canvas.progress = .25
    assert canvas.index_at(QPointF(center.x() + r, center.y() + r)) == -1
    canvas.deleteLater()


def test_hover_motion_can_finish_immediately_and_does_not_replay_entry(chart):
    chart.setProperty('reduceMotion', False)
    chart.canvas.set_hover(1)
    assert chart.canvas.hover_animation.state() == QAbstractAnimation.State.Running
    wait_until(lambda: chart.canvas.hover_progress == 1., 'Hover highlight did not settle')
    chart.canvas.set_hover(0)
    chart.setProperty('reduceMotion', True)
    chart.finish_motion()
    assert chart.canvas.progress == chart.legend.progress == chart.canvas.hover_progress == 1.
    assert chart.canvas.hover_animation.state() == QAbstractAnimation.State.Stopped
    assert chart.animation.state() == QAbstractAnimation.State.Stopped


def test_compact_chart_stacks_legend_and_keeps_zero_categories_reachable(chart):
    chart.resize(530, 600)
    QApplication.processEvents()
    assert chart.charts_layout.direction() == QBoxLayout.Direction.TopToBottom
    chart.choice.setCurrentIndex(1)
    assert chart.canvas.donut_spans()[-1][2] == 0
    assert chart.legend.index_at(QPointF(25, 78)) == 2


def test_export_is_final_frame_without_live_hover_selection_or_played_mutation(chart, tmp_path):
    chart.choice.setCurrentIndex(1)
    reference = chart.render_image(title='虚构图表', subtitle='测试口径', description='每位好友可计入多个类别。')
    chart._progress_changed(.25)
    chart._hover_changed(1)
    chart._selection_changed(1)
    before_played = set(chart.played)
    result = chart.render_image(title='虚构图表', subtitle='测试口径', description='每位好友可计入多个类别。')
    assert result == reference
    assert chart.canvas.progress == .25 and chart.canvas.selected_index == chart.canvas.hover_index == 1
    assert chart.played == before_played
    target = tmp_path / '图表.png'
    chart.export_png(target, title='虚构图表', subtitle='测试口径', description='每位好友可计入多个类别。')
    assert target.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    assert QImage(str(target)).size() == result.size()


def test_export_failed_encoding_preserves_existing_file(chart, tmp_path, monkeypatch):
    target = tmp_path / 'keep.png'
    target.write_bytes(b'original image bytes')

    class FailedImage:
        def save(self, device, _format):
            device.write(b'partially encoded bytes')
            return False

    monkeypatch.setattr(chart, 'render_image', lambda *args: FailedImage())
    with pytest.raises(OSError, match='原文件已保留'):
        chart.export_png(target)
    assert target.read_bytes() == b'original image bytes'
    assert list(tmp_path.iterdir()) == [target]


def test_export_includes_long_legends_and_rejects_oversize_without_touching_file(app, tmp_path):
    widget = DistributionChart([('长分类名称' * 12 + str(i), i) for i in range(24)], '长图', set())
    widget.choice.setCurrentIndex(1)
    image = widget.render_image()
    assert image.height() > 1200
    widget.close()
    widget.deleteLater()
    widget = DistributionChart([(str(i), 1) for i in range(1000)], '超大图', set())
    target = tmp_path / 'preserve.png'
    target.write_bytes(b'unchanged')
    with pytest.raises(ValueError, match='分类过多'):
        widget.export_png(target)
    assert target.read_bytes() == b'unchanged'
    widget.choice.setCurrentIndex(1)
    with pytest.raises(ValueError, match='图片大小限制'):
        widget.export_png(target)
    widget.close()
    widget.deleteLater()


@pytest.mark.parametrize('counts', [[], [('未填写', 0)]])
def test_empty_and_all_zero_exports_are_valid_without_unknown_as_zero_invention(app, counts):
    widget = DistributionChart(counts, '空数据', set())
    widget.choice.setCurrentIndex(1)
    assert widget.canvas.donut_spans() == []
    assert not widget.render_image().isNull()
    assert widget.counts == counts
    widget.close()
    widget.deleteLater()
