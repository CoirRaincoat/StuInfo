"""Short, interruptible Qt motions. No animation owns or commits application state."""
from math import hypot
from PySide6.QtCore import QObject, QEvent, Qt, QPointF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (QApplication, QWidget, QAbstractButton, QComboBox, QTabBar,
    QMenu, QAbstractItemView, QStackedWidget, QTabWidget, QLineEdit, QPlainTextEdit, QAbstractSlider)


def motion_enabled(widget):
    return not bool(widget.window().property('reduceMotion'))


class Ripple(QWidget):
    def __init__(self, parent, origin, bounds=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setGeometry(bounds if bounds is not None else parent.rect())
        self.origin = QPointF(origin - self.pos())
        self.progress = 0.0
        self.radius = max(hypot(self.origin.x() - x, self.origin.y() - y)
                          for x in (0, self.width()) for y in (0, self.height()))
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(360)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._frame)
        self.animation.finished.connect(self.deleteLater)
        self.show()
        self.raise_()
        self.animation.start()

    def _frame(self, value):
        self.progress = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor('#a291c5')
        color.setAlpha(round(65 * (1 - self.progress)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(self.origin, self.radius * self.progress, self.radius * self.progress)


class TransitionCover(QWidget):
    def __init__(self, parent, snapshot):
        # Finish a previous transition before capturing a new one, never stack effects.
        for previous in parent.findChildren(TransitionCover, options=Qt.FindChildOption.FindDirectChildrenOnly):
            previous.hide()
            previous.deleteLater()
        super().__init__(parent)
        self.snapshot = snapshot
        self.progress = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setGeometry(parent.rect())
        self.animation = QVariantAnimation(self)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setDuration(170)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._frame)
        self.animation.finished.connect(self.deleteLater)
        self.show()
        self.raise_()
        self.animation.start()

    def _frame(self, value):
        self.progress = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setOpacity(1 - self.progress)
        painter.drawPixmap(round(-12 * self.progress), 0, self.snapshot)


class AnimatedStack(QStackedWidget):
    def setCurrentWidget(self, widget):
        old = self.currentWidget()
        snapshot = old.grab() if old and old != widget and self.isVisible() and motion_enabled(self) else None
        super().setCurrentWidget(widget)
        if snapshot is not None:
            TransitionCover(self, snapshot)


class AnimatedTabs(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.previous = None
        self.currentChanged.connect(self._transition)

    def _transition(self, index):
        current = self.widget(index)
        if self.previous is not None and current and self.isVisible() and motion_enabled(self):
            TransitionCover(current, self.previous.grab())
        self.previous = current


class ClickFeedback(QObject):
    """One filter covers existing and dynamically-created Qt controls in this window."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        mouse = event.type() == QEvent.Type.MouseButtonPress
        keyboard = event.type() == QEvent.Type.KeyPress
        if not mouse and not keyboard:
            return False
        if mouse and event.button() != Qt.MouseButton.LeftButton:
            return False
        if keyboard and (event.isAutoRepeat() or not isinstance(obj, QAbstractButton) or
                         event.key() not in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            return False
        if not isinstance(obj, QWidget) or not obj.isEnabled() or not motion_enabled(self.window):
            return False
        if obj != self.window and not self.window.isAncestorOf(obj):
            return False
        bounds = None
        position = event.position().toPoint() if mouse else obj.rect().center()
        view = obj.parentWidget()
        if isinstance(view, QAbstractItemView) and obj == view.viewport():
            index = view.indexAt(position)
            if not index.isValid():
                return False
            bounds = view.visualRect(index)
            # The friend list handles its own full-row ripple before possible navigation.
            if obj.property('rowMotion'):
                return False
        elif isinstance(obj, QTabBar):
            tab = obj.tabAt(position)
            if tab < 0:
                return False
            bounds = obj.tabRect(tab)
        elif isinstance(obj, QMenu):
            action = obj.actionAt(position)
            if not action or not action.isEnabled():
                return False
            bounds = obj.actionGeometry(action)
        elif isinstance(view, QPlainTextEdit) and obj == view.viewport():
            pass
        elif not isinstance(obj, (QAbstractButton, QComboBox, QLineEdit, QAbstractSlider)):
            return False
        # Cap overlapping ripples during rapid input without delaying a single click.
        for previous in obj.findChildren(Ripple, options=Qt.FindChildOption.FindDirectChildrenOnly)[:-2]:
            previous.hide()
            previous.deleteLater()
        Ripple(obj, position, bounds)
        return False


class DrawerWorkspace(QWidget):
    """Desktop list + sliding details; compact windows use one pane at a time."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.panes = []
        self.fraction = 0.0
        self.opened = False
        self.compact = False
        self.preferred_width = 410
        self.handle = QWidget(self)
        self.handle.setCursor(Qt.CursorShape.SplitHCursor)
        self.handle.installEventFilter(self)
        self.handle.hide()
        self.dragging = False
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.OutBack)
        self.animation.valueChanged.connect(self._frame)
        self.animation.finished.connect(self._settled)

    def addWidget(self, widget):
        widget.setParent(self)
        self.panes.append(widget)
        if len(self.panes) == 2:
            widget.hide()

    def set_open(self, opened, compact):
        changed = opened != self.opened
        compact_changed = compact != self.compact
        self.opened, self.compact = opened, compact
        if len(self.panes) < 2:
            return
        self.panes[0].setVisible(not compact or not opened)
        if opened:
            self.panes[1].show()
        if changed or compact_changed:
            self.animation.stop()
            target = float(opened)
            # Closing eases toward zero without the opening spring's negative overshoot.
            self.animation.setEasingCurve(QEasingCurve.Type.OutBack if opened else QEasingCurve.Type.OutCubic)
            if changed and motion_enabled(self) and self.isVisible():
                self.animation.setStartValue(self.fraction)
                self.animation.setEndValue(target)
                self.animation.start()
            else:
                self.fraction = target
                self._settled()
        self._layout()

    def finish_motion(self):
        self.animation.stop()
        self.fraction = float(self.opened)
        self._settled()

    def _frame(self, value):
        self.fraction = max(0.0, value)
        self._layout()

    def _settled(self):
        self.fraction = float(self.opened)
        if len(self.panes) == 2:
            self.panes[1].setVisible(self.opened)
        self._layout()

    def resizeEvent(self, event):
        self._layout()

    def _layout(self):
        if len(self.panes) < 2:
            return
        width, height = self.width(), self.height()
        drawer = width if self.compact else min(max(340, self.preferred_width), max(340, width - 320))
        reveal = min(width, round(drawer * self.fraction))
        gap = 8 if reveal and not self.compact else 0
        self.panes[0].setGeometry(0, 0, width if self.compact else max(0, width - reveal - gap), height)
        self.panes[1].setGeometry(width - reveal, 0, max(drawer, reveal), height)
        self.handle.setGeometry(width - reveal - gap, 0, gap, height)
        self.handle.setVisible(self.opened and not self.compact)
        self.panes[1].raise_()

    def eventFilter(self, obj, event):
        if obj == self.handle:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self.finish_motion()
                self.dragging = True
                return True
            if event.type() == QEvent.Type.MouseMove and self.dragging:
                x = self.mapFromGlobal(event.globalPosition().toPoint()).x()
                self.preferred_width = min(max(340, self.width() - x), max(340, self.width() - 320))
                self._layout()
                return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self.dragging = False
                return True
        return super().eventFilter(obj, event)
