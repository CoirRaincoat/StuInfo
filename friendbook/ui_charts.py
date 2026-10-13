"""Native charts: real category hit testing, restrained motion and atomic PNG export."""
from html import escape
from math import atan2, degrees, hypot

from PySide6.QtCore import Qt, QRectF, QVariantAnimation, QEasingCurve, Signal, QSaveFile, QIODevice
from PySide6.QtGui import QPainter, QColor, QPen, QPalette, QImage, QFontMetrics
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QComboBox,
                               QScrollArea, QFrame, QLabel, QSizePolicy)


COLORS = ('#9281b8', '#6c9ba6', '#c6a56f', '#8da884', '#bd879b', '#879bc3', '#ba997e', '#899b98')


def chart_color(index):
    if index < len(COLORS):
        return QColor(COLORS[index])
    return QColor.fromHsv((index * 137 + 262) % 360, 90, 175)


def category_text(counts, index):
    if not 0 <= index < len(counts):
        return ''
    name, value = counts[index]
    total = sum(number for _, number in counts)
    ratio = value / total if total else 0.
    return f'{name}：{value} · 占统计归属次数 {ratio:.1%}'


class CategoryWidget(QWidget):
    """Canvas and legend share hover/selection state; indices preserve category identity."""
    hovered = Signal(int)
    activated = Signal(int)
    selection_changed = Signal(int)

    def __init__(self, counts, parent=None):
        super().__init__(parent)
        self.counts = list(counts)
        self.progress = 1.
        self.hover_index = self.selected_index = -1
        self._pressed_index = -1
        self.hover_progress = 1.
        self.hover_animation = QVariantAnimation(self)
        self.hover_animation.setDuration(130)
        self.hover_animation.setStartValue(0.)
        self.hover_animation.setEndValue(1.)
        self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hover_animation.valueChanged.connect(self._hover_progress_changed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _hover_progress_changed(self, value):
        if self.window().property('reduceMotion'):
            self.hover_animation.stop()
            value = 1.
        self.hover_progress = float(value)
        self.update()

    def set_hover(self, index):
        if index == self.hover_index:
            return
        self.hover_animation.stop()
        self.hover_index = index
        animate = index >= 0 and not bool(self.window().property('reduceMotion'))
        self.hover_progress = 0. if animate else 1.
        if animate:
            self.hover_animation.start()
        self.update()

    def set_selected(self, index):
        if index == self.selected_index:
            return
        self.selected_index = index
        self.selection_changed.emit(index)
        self.update()

    def mouseMoveEvent(self, event):
        index = self.index_at(event.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if index >= 0 else Qt.CursorShape.ArrowCursor)
        # Explicit plain-text HTML escaping prevents user labels becoming tooltip markup.
        self.setToolTip(f'<qt>{escape(category_text(self.counts, index))}</qt>' if index >= 0 else '')
        if index != self.hover_index:
            self.set_hover(index)
            self.hovered.emit(index)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.set_hover(-1)
        self.hovered.emit(-1)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed_index = self.index_at(event.position())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.index_at(event.position())
            pressed = self._pressed_index
            self._pressed_index = -1
            if index >= 0 and index == pressed:
                self.set_selected(index)
                self.activated.emit(index)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self.counts and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Right,
                                          Qt.Key.Key_Down, Qt.Key.Key_Home, Qt.Key.Key_End):
            index = self.selected_index
            if event.key() == Qt.Key.Key_Home:
                index = 0
            elif event.key() == Qt.Key.Key_End:
                index = len(self.counts) - 1
            elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
                index = min(len(self.counts) - 1, index + 1)
            else:
                index = max(0, index - 1)
            self.set_selected(index)
            self.set_hover(index)
            self.hovered.emit(index)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Space) and self.selected_index >= 0:
            self.activated.emit(self.selected_index)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.set_selected(-1)
            self.set_hover(-1)
            self.hovered.emit(-1)
            event.accept()
            return
        super().keyPressEvent(event)

    def active_index(self):
        return self.hover_index if self.hover_index >= 0 else self.selected_index

    def category_color(self, index):
        color = chart_color(index)
        if index == self.hover_index:
            return color.lighter(round(100 + 16 * self.hover_progress))
        if self.active_index() >= 0 and index != self.active_index():
            color.setAlpha(145)
        return color


class ChartLegend(CategoryWidget):
    def __init__(self, counts, parent=None):
        super().__init__(counts, parent)
        self.setMinimumWidth(205)
        self.setMinimumHeight(max(80, len(self.counts) * 30 + 12))
        self.setAccessibleName('统计图例；方向键选择分类，回车查看好友')

    def index_at(self, point):
        index = int((point.y() - 6) // 30)
        return index if self.rect().contains(point.toPoint()) and 0 <= index < len(self.counts) else -1

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
            if index == self.active_index():
                background = self.palette().highlight().color()
                background.setAlpha(35)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(background)
                painter.drawRoundedRect(QRectF(0, y - 2, self.width(), 28), 5, 5)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.category_color(index))
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


class ChartCanvas(CategoryWidget):
    """Bar heights and donut sweep share a normalized, testable progress value."""
    def __init__(self, counts, parent=None):
        super().__init__(counts, parent)
        self.mode = 'bar'
        self.setMinimumHeight(330)
        self.setAccessibleName('统计图；方向键选择分类，回车查看好友')
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

    def donut_geometry(self):
        size = max(1., min(self.width() - 50., self.height() - 54., 280.))
        outer = QRectF((self.width() - size) / 2, 24, size, size)
        thickness = size * .18
        return outer, outer.adjusted(thickness / 2, thickness / 2, -thickness / 2, -thickness / 2), thickness

    def index_at(self, point):
        if self.mode == 'donut':
            outer, _, thickness = self.donut_geometry()
            dx, dy = point.x() - outer.center().x(), point.y() - outer.center().y()
            radius = hypot(dx, dy)
            if not outer.width() / 2 - thickness <= radius <= outer.width() / 2:
                return -1
            angle = (degrees(atan2(dy, dx)) + 90) % 360
            for index, start, span in self.donut_spans():
                if span > 0 and start <= angle < start + span:
                    return index
            return -1
        step = (self.width() - 52) / max(1, len(self.counts))
        baseline = self.height() - 66
        for index, (_, _, rect) in enumerate(self.bar_rects()):
            # A zero has no bar area; its baseline and label remain usable targets.
            target = QRectF(rect.center().x() - step / 2, min(rect.top() - 5, baseline - 6),
                            step, baseline + 46 - min(rect.top() - 5, baseline - 6))
            if target.contains(point):
                return index
        return -1

    def paintEvent(self, event):
        painter = QPainter(self)
        self.draw_chart(painter)

    def draw_chart(self, painter):
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
            painter.setBrush(self.category_color(index))
            if rect.height() > 0:
                painter.drawRoundedRect(rect, min(4., rect.height() / 2), min(4., rect.height() / 2))
                if index == self.selected_index:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(self.palette().text().color(), 1.5))
                    painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 5, 5)
            painter.setPen(self.palette().text().color())
            painter.drawText(QRectF(rect.center().x() - 30, rect.top() - 23, 60, 21),
                             Qt.AlignmentFlag.AlignCenter, str(value))
            title = painter.fontMetrics().elidedText(str(name), Qt.TextElideMode.ElideRight, int(step - 6))
            painter.drawText(QRectF(rect.center().x() - step / 2 + 3, baseline + 9, step - 6, 34),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, title)

    def _paint_donut(self, painter):
        outer, ring, thickness = self.donut_geometry()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self.palette().alternateBase(), thickness))
        painter.drawEllipse(ring)
        for index, start, span in self.donut_spans():
            if span <= 0:
                continue
            emphasis = 1. + (.10 * self.hover_progress if index == self.hover_index else 0.)
            if index == self.selected_index:
                emphasis = max(emphasis, 1.08)
            painter.setPen(QPen(self.category_color(index), thickness * emphasis,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            painter.drawArc(ring, round((90 - start) * 16), -round(span * 16))
        painter.setPen(self.palette().text().color())
        base_font = painter.font()
        font = painter.font()
        # App themes use pixel fonts, where pointSize() is -1. Scale the actual
        # font metrics so native Windows DPI and exported figures stay consistent.
        font.setPixelSize(max(28, painter.fontMetrics().height() * 2))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(outer.adjusted(0, -10, 0, -10), Qt.AlignmentFlag.AlignCenter,
                         str(self.counts[self.active_index()][1] if self.active_index() >= 0
                             else sum(value for _, value in self.counts)))
        painter.setFont(base_font)
        text = '统计归属次数'
        if self.active_index() >= 0:
            name, value = self.counts[self.active_index()]
            total = sum(number for _, number in self.counts)
            text = painter.fontMetrics().elidedText(str(name), Qt.TextElideMode.ElideRight,
                                                   int(outer.width() - thickness * 2 - 12))
            text += f'\n{value / total:.1%}' if total else '\n0.0%'
        painter.drawText(outer.adjusted(thickness, 43, -thickness, 43), Qt.AlignmentFlag.AlignCenter, text)


class DistributionChart(QWidget):
    category_activated = Signal(int)

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
        charts = self.charts_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
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
        self.summary = QLabel('悬停查看数值与比例；点击图表或图例查看对应好友。')
        self.summary.setObjectName('muted')
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.summary)
        for widget in (self.canvas, self.legend):
            widget.hovered.connect(self._hover_changed)
            widget.selection_changed.connect(self._selection_changed)
            widget.activated.connect(self._activate)
        self.choice.currentIndexChanged.connect(self._mode_changed)

    def _hover_changed(self, index):
        self.canvas.set_hover(index)
        self.legend.set_hover(index)
        self._update_summary()

    def _selection_changed(self, index):
        self.canvas.set_selected(index)
        self.legend.set_selected(index)
        self._update_summary()

    def _activate(self, index):
        if 0 <= index < len(self.counts):
            self._selection_changed(index)
            self.category_activated.emit(index)

    def _update_summary(self):
        text = category_text(self.counts, self.canvas.active_index())
        self.summary.setText(text or '悬停查看数值与比例；点击图表或图例查看对应好友。')

    def resizeEvent(self, event):
        direction = (QBoxLayout.Direction.TopToBottom if event.size().width() < 680
                     else QBoxLayout.Direction.LeftToRight)
        self.charts_layout.setDirection(direction)
        self.charts_layout.setStretch(0, 0 if direction == QBoxLayout.Direction.TopToBottom else 3)
        self.charts_layout.setStretch(1, 0 if direction == QBoxLayout.Direction.TopToBottom else 2)
        super().resizeEvent(event)

    def finish_motion(self):
        self.animation.stop()
        self._progress_changed(1.)
        for widget in (self.canvas, self.legend):
            widget.hover_animation.stop()
            widget.hover_progress = 1.
            widget.update()

    def render_image(self, title='', subtitle='', description=''):
        """Render all categories at their final frame, without changing live UI state.

        Full labels wrap in the export legend. Size limits reject oversized exports
        explicitly instead of silently clipping categories or allocating unbounded images.
        """
        canvas_width = max(640, len(self.counts) * 62 + 52) if self.canvas.mode == 'bar' else 640
        legend_width = 360
        width = canvas_width + legend_width + 100
        if width > 8192:
            raise ValueError('分类过多，柱状图导出宽度超出限制；请切换为环形图后重试。')
        font = self.font()
        metrics = QFontMetrics(font)
        wrap = Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere

        def text_height(text, available):
            return metrics.boundingRect(0, 0, available, 100000, int(wrap), str(text)).height() if text else 0

        heading_height = text_height(title or str(self.key), width - 64) + 16
        subtitle_height = text_height(subtitle, width - 64) + (12 if subtitle else 0)
        top = 40 + heading_height + subtitle_height
        legend_rows = []
        for index, (name, value) in enumerate(self.counts):
            height = text_height(name, legend_width - 28) + metrics.height() + 18
            legend_rows.append((index, height))
        plot_height = max(360, sum(height for _, height in legend_rows))
        description_height = text_height(description, width - 64) + (28 if description else 0)
        height = top + plot_height + description_height + 42
        if height > 8192 or width * height > 32_000_000:
            raise ValueError('分类或文字过多，完整图表超出图片大小限制；请减少分类后重试。')
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        if image.isNull():
            raise OSError('没有足够内存生成图表，请关闭其他窗口后重试。')
        image.fill(self.palette().color(QPalette.ColorRole.Base))
        painter = QPainter(image)
        canvas = ChartCanvas(self.counts)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(self.palette().text().color())
            painter.setFont(font)
            title_font = painter.font()
            title_font.setBold(True)
            painter.setFont(title_font)
            painter.drawText(QRectF(32, 28, width - 64, heading_height), int(wrap), title or str(self.key))
            painter.setFont(font)
            if subtitle:
                painter.drawText(QRectF(32, 28 + heading_height, width - 64, subtitle_height), int(wrap), subtitle)
            canvas.setPalette(self.palette())
            canvas.setFont(font)
            canvas.set_mode(self.canvas.mode)
            canvas.resize(canvas_width, 360)
            painter.save()
            painter.translate(24, top)
            canvas.draw_chart(painter)
            painter.restore()
            y = top + 6
            total = sum(value for _, value in self.counts)
            for index, row_height in legend_rows:
                name, value = self.counts[index]
                x = canvas_width + 60
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(chart_color(index))
                painter.drawRoundedRect(QRectF(x, y + 3, 11, 11), 3, 3)
                painter.setPen(self.palette().text().color())
                name_height = row_height - metrics.height() - 18
                painter.drawText(QRectF(x + 25, y, legend_width - 28, name_height), int(wrap), str(name))
                ratio = value / total if total else 0.
                painter.drawText(QRectF(x + 25, y + name_height + 4, legend_width - 28, metrics.height() + 4),
                                 Qt.AlignmentFlag.AlignLeft, f'{value} · 占统计归属次数 {ratio:.1%}')
                y += row_height
            if description:
                painter.drawText(QRectF(32, top + plot_height + 20, width - 64, description_height),
                                 int(wrap), description)
        finally:
            painter.end()
            canvas.deleteLater()
        return image

    def export_png(self, path, title='', subtitle='', description=''):
        """Atomically replace only after complete PNG encoding; preserve the old file on failure."""
        image = self.render_image(title, subtitle, description)
        target = QSaveFile(str(path))
        target.setDirectWriteFallback(False)
        if not target.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(f'无法写入图表文件：{target.errorString()}')
        try:
            if not image.save(target, 'PNG'):
                raise OSError('图表 PNG 编码或写入失败，原文件已保留。')
            if not target.commit():
                raise OSError(f'无法完成图表保存：{target.errorString()}')
        except Exception:
            target.cancelWriting()
            raise

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
        self.finish_motion()
        super().hideEvent(event)
