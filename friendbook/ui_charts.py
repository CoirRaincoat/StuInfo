"""Native statistical charts with entry motion limited to their first appearance."""
from PySide6.QtCore import Qt, QRectF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QPen, QPalette
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QScrollArea, QFrame


COLORS = ('#9281b8', '#6c9ba6', '#c6a56f', '#8da884', '#bd879b', '#879bc3', '#ba997e', '#899b98')


def chart_color(index):
    if index < len(COLORS):
        return QColor(COLORS[index])
    return QColor.fromHsv((index * 137 + 262) % 360, 90, 175)


class ChartLegend(QWidget):
    def __init__(self, counts, parent=None):
        super().__init__(parent)
        self.counts = counts
        self.progress = 1.0
        self.setMinimumWidth(205)
        self.setMinimumHeight(max(80, len(counts) * 30 + 12))
        total = sum(value for _, value in counts)
        self.setToolTip('\n'.join(f'{name}：{value}（{value / total:.1%}）' if total else f'{name}：0'
                                  for name, value in counts))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(value for _, value in self.counts)
        for index, (name, value) in enumerate(self.counts):
            # All legends finish together, while their entry starts in a short cascade.
            delay = min(index, 7) * .025
            shown = max(0., min(1., (self.progress - delay) / (1. - delay)))
            painter.save()
            painter.setOpacity(shown)
            painter.translate((1. - shown) * 14., 0)
            y = index * 30 + 6
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(chart_color(index))
            painter.drawRoundedRect(QRectF(4, y + 5, 10, 10), 3, 3)
            painter.setPen(self.palette().text().color())
            right = f'{value} · {value / total:.1%}' if total else '0 · 0.0%'
            right_width = painter.fontMetrics().horizontalAdvance(right) + 12
            title_width = max(20, self.width() - right_width - 26)
            title = painter.fontMetrics().elidedText(str(name), Qt.TextElideMode.ElideRight, title_width)
            painter.drawText(QRectF(23, y, title_width, 23), Qt.AlignmentFlag.AlignVCenter, title)
            painter.drawText(QRectF(self.width() - right_width, y, right_width - 4, 23),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, right)
            painter.restore()


class ChartCanvas(QWidget):
    """Bar heights and donut sweep share a normalized, testable progress value."""
    def __init__(self, counts, parent=None):
        super().__init__(parent)
        self.counts = counts
        self.mode = 'bar'
        self.progress = 1.0
        self.setMinimumHeight(330)
        self.setToolTip('\n'.join(f'{name}：{value}' for name, value in counts))
        self.set_mode('bar')

    def set_mode(self, mode):
        self.mode = mode
        self.setMinimumWidth(max(320, len(self.counts) * 62 + 48) if mode == 'bar' else 300)
        self.updateGeometry()
        self.update()

    def bar_rects(self):
        area = QRectF(38, 26, max(1, self.width() - 52), max(1, self.height() - 92))
        largest = max([1] + [value for _, value in self.counts])
        step = area.width() / max(1, len(self.counts))
        width = min(48., step * .66)
        return [(name, value, QRectF(area.left() + step * (index + .5) - width / 2,
                    area.bottom() - area.height() * value / largest * self.progress,
                    width, area.height() * value / largest * self.progress))
                for index, (name, value) in enumerate(self.counts)]

    def donut_spans(self):
        total = sum(value for _, value in self.counts)
        if not total:
            return []
        revealed = 360. * self.progress
        start = 0.
        spans = []
        for index, (_, value) in enumerate(self.counts):
            full = 360. * value / total
            spans.append((index, start, max(0., min(full, revealed - start))))
            start += full
        return spans

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.counts:
            painter.setPen(self.palette().text().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '暂无可统计的数据')
            return
        if self.mode == 'donut':
            self._paint_donut(painter)
        else:
            self._paint_bars(painter)

    def _paint_bars(self, painter):
        baseline = self.height() - 66
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Mid), 1))
        painter.drawLine(38, baseline, self.width() - 14, baseline)
        largest = max([1] + [value for _, value in self.counts])
        painter.setPen(self.palette().text().color())
        painter.drawText(QRectF(0, 16, 31, 22), Qt.AlignmentFlag.AlignRight, str(largest))
        painter.drawText(QRectF(0, baseline - 10, 31, 22), Qt.AlignmentFlag.AlignRight, '0')
        step = (self.width() - 52) / max(1, len(self.counts))
        for index, (name, value, rect) in enumerate(self.bar_rects()):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(chart_color(index))
            if rect.height() > 0:
                painter.drawRoundedRect(rect, min(4., rect.height() / 2), min(4., rect.height() / 2))
            painter.setPen(self.palette().text().color())
            painter.drawText(QRectF(rect.center().x() - 30, rect.top() - 23, 60, 21),
                             Qt.AlignmentFlag.AlignCenter, str(value))
            title = painter.fontMetrics().elidedText(str(name), Qt.TextElideMode.ElideRight, int(step - 6))
            painter.drawText(QRectF(rect.center().x() - step / 2 + 3, baseline + 9, step - 6, 34),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, title)

    def _paint_donut(self, painter):
        size = min(self.width() - 50., self.height() - 54., 280.)
        outer = QRectF((self.width() - size) / 2, 24, size, size)
        thickness = size * .18
        ring = outer.adjusted(thickness / 2, thickness / 2, -thickness / 2, -thickness / 2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self.palette().alternateBase(), thickness))
        painter.drawEllipse(ring)
        for index, start, span in self.donut_spans():
            if span <= 0:
                continue
            painter.setPen(QPen(chart_color(index), thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            painter.drawArc(ring, round((90 - start) * 16), -round(span * 16))
        painter.setPen(self.palette().text().color())
        font = painter.font()
        font.setPointSize(font.pointSize() + 12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(outer.adjusted(0, -10, 0, -10), Qt.AlignmentFlag.AlignCenter,
                         str(sum(value for _, value in self.counts)))
        font.setPointSize(max(9, font.pointSize() - 13))
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(outer.adjusted(0, 43, 0, 43), Qt.AlignmentFlag.AlignCenter, '统计归属次数')


class DistributionChart(QWidget):
    def __init__(self, counts, key, played, parent=None):
        super().__init__(parent)
        self.counts = list(counts)
        self.key = key
        self.played = played
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(720)
        self.animation.setStartValue(0.)
        self.animation.setEndValue(1.)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._progress_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.choice = QComboBox()
        self.choice.setAccessibleName('统计图类型')
        self.choice.addItems(['柱状图', '环形图'])
        row = QHBoxLayout()
        row.addWidget(self.choice)
        row.addStretch()
        layout.addLayout(row)
        charts = QHBoxLayout()
        charts.setSpacing(20)
        self.canvas = ChartCanvas(self.counts)
        viewport = QScrollArea()
        viewport.setFrameShape(QFrame.Shape.NoFrame)
        viewport.setWidgetResizable(True)
        viewport.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        viewport.setMinimumHeight(350)
        viewport.setWidget(self.canvas)
        charts.addWidget(viewport, 3)
        self.legend = ChartLegend(self.counts)
        charts.addWidget(self.legend, 2)
        charts.setAlignment(self.legend, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(charts)
        self.choice.currentIndexChanged.connect(self._mode_changed)

    def _progress_changed(self, progress):
        self.canvas.progress = self.legend.progress = float(progress)
        self.canvas.update()
        self.legend.update()

    def _mode_changed(self, index):
        self.canvas.set_mode('donut' if index else 'bar')
        if self.isVisible():
            self._enter()

    def _enter(self):
        self.animation.stop()
        key = (self.key, self.canvas.mode)
        animate = key not in self.played and not bool(self.window().property('reduceMotion'))
        self.played.add(key)
        self._progress_changed(0. if animate else 1.)
        if animate:
            self.animation.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._enter()

    def hideEvent(self, event):
        self.animation.stop()
        self._progress_changed(1.)
        super().hideEvent(event)
