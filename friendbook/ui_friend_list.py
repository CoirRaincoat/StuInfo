"""Row-level interaction and handle-only dragging; all mutations are UUID commands."""
from PySide6.QtCore import Qt, QTimer, Signal, QPoint, QRect, QEasingCurve, QVariantAnimation, QEvent
from PySide6.QtGui import QPainter, QColor, QPen, QCursor
from PySide6.QtWidgets import (QTableWidget, QStyledItemDelegate, QStyleOptionViewItem,
                               QStyle, QLabel)
from .ui_motion import Ripple, motion_enabled


class FriendDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        view = self.parent()
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        # Keep keyboard focus on the table without drawing a border around one cell.
        opt.state &= ~(QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_HasFocus)
        if index.row() == view.hovered_row:
            opt.state |= QStyle.StateFlag.State_MouseOver
        if view.management:
            uid = view.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
            opt.state &= ~QStyle.StateFlag.State_Selected
            if uid in view.checked_ids:
                opt.state |= QStyle.StateFlag.State_Selected
                opt.backgroundBrush = opt.palette.highlight()
        opt.showDecorationSelected = True
        if view.management and index.column() == 4:
            opt.text = ''
        view.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, view)
        if view.management and index.column() == 4:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = QColor('#9281b8' if view.reorder_allowed else '#999ba5')
            color.setAlpha(230 if view.reorder_allowed else 100)
            painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            center = option.rect.center()
            for offset in (-5, 0, 5):
                painter.drawLine(center.x() - 7, center.y() + offset, center.x() + 7, center.y() + offset)
            painter.restore()


class FriendsTable(QTableWidget):
    toggle_requested = Signal(str)
    select_all_requested = Signal()
    reorder_requested = Signal(list, object)

    def __init__(self, parent=None):
        super().__init__(0, 4, parent)
        self.management = False
        self.reorder_allowed = False
        self.checked_ids = set()
        self.hovered_row = -1
        self.setMouseTracking(True)
        self.setVerticalScrollMode(self.ScrollMode.ScrollPerPixel)
        self.viewport().setMouseTracking(True)
        self.viewport().setProperty('rowMotion', True)
        self.setItemDelegate(FriendDelegate(self))
        self.setObjectName('friendsTable')
        self._pressed_handle = None
        self._press_pos = QPoint()
        self._pointer = QPoint()
        self._drag_ids = []
        self._drag_slot = None
        self._ghost = None
        self._follow_y = 0.0
        self._long_press = QTimer(self)
        self._long_press.setSingleShot(True)
        self._long_press.setInterval(180)
        self._long_press.timeout.connect(self._begin_drag)
        self._drag_timer = QTimer(self)
        self._drag_timer.setInterval(16)
        self._drag_timer.timeout.connect(self._drag_frame)
        self._lift = QVariantAnimation(self)
        self._lift.setDuration(160)
        self._lift.setStartValue(0.0)
        self._lift.setEndValue(1.0)
        self._lift.setEasingCurve(QEasingCurve.Type.OutBack)
        self._lift.valueChanged.connect(lambda _: self._place_ghost())
        self.verticalScrollBar().valueChanged.connect(lambda _: self.viewport().update())

    def configure_management(self, enabled, checked_ids, reorder_allowed):
        self.cancel_drag()
        self.management = enabled
        self.checked_ids = set(checked_ids)
        self.reorder_allowed = reorder_allowed
        self.setColumnCount(5 if enabled else 4)
        self.viewport().update()

    def row_rect(self, row):
        return QRect(0, self.rowViewportPosition(row), self.viewport().width(), self.rowHeight(row))

    def _uid(self, row):
        item = self.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        row = self.rowAt(pos.y())
        uid = self._uid(row)
        if event.button() != Qt.MouseButton.LeftButton or not uid:
            return super().mousePressEvent(event)
        self.setFocus()
        if motion_enabled(self):
            for ripple in self.viewport().findChildren(Ripple):
                ripple.hide()
                ripple.deleteLater()
            Ripple(self.viewport(), pos, self.row_rect(row))
        if self.management:
            if self.columnAt(pos.x()) == 4:
                if self.reorder_allowed:
                    self._pressed_handle = uid
                    self._press_pos = self._pointer = pos
                    self._long_press.start()
                event.accept()
                return
            self.setCurrentCell(row, 0)
            self.toggle_requested.emit(uid)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._pointer = event.position().toPoint()
        row = self.rowAt(self._pointer.y())
        if row != self.hovered_row:
            self.hovered_row = row
            self.viewport().update()
        handle = self.management and self.columnAt(self._pointer.x()) == 4
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor if self._drag_ids else (
            Qt.CursorShape.OpenHandCursor if handle and self.reorder_allowed else Qt.CursorShape.ArrowCursor))
        if self._pressed_handle:
            # Moving immediately also works with a desktop mouse; a stationary hold lifts at 180 ms.
            if not self._drag_ids and (self._pointer - self._press_pos).manhattanLength() >= 8:
                self._begin_drag()
            self._update_slot()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _begin_drag(self):
        self._long_press.stop()
        if not self._pressed_handle or not self.reorder_allowed or not self.isEnabled():
            return
        selected = self.checked_ids if self._pressed_handle in self.checked_ids else {self._pressed_handle}
        self._drag_ids = [self._uid(row) for row in range(self.rowCount()) if self._uid(row) in selected]
        row = next(row for row in range(self.rowCount()) if self._uid(row) == self._pressed_handle)
        # A local visual snapshot only; the model and linked list stay unchanged until drop succeeds.
        pixmap = self.viewport().grab(self.row_rect(row))
        self._ghost = QLabel(self.viewport())
        self._ghost.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._ghost.setPixmap(pixmap)
        self._ghost.resize(self.viewport().width() - 8, self.rowHeight(row))
        self._ghost.setStyleSheet('QLabel { border: 1px solid #9281b8; border-radius: 6px; background: palette(base); }')
        if len(self._drag_ids) > 1:
            count = QLabel(f'移动 {len(self._drag_ids)} 位', self._ghost)
            count.setStyleSheet('padding: 4px 10px; background: #79659f; color: white; border-radius: 5px;')
            count.adjustSize()
            count.move(max(0, self._ghost.width() - count.width() - 42), 6)
        self._follow_y = self.rowViewportPosition(row)
        self._place_ghost()
        self._ghost.show()
        self._ghost.raise_()
        if motion_enabled(self):
            self._lift.start()
        self._drag_timer.start()
        self._update_slot()

    def _place_ghost(self):
        if self._ghost:
            lift = self._lift.currentValue() or 0.0
            self._ghost.move(round(4 * lift), round(self._follow_y - 2 * lift))

    def _drag_frame(self):
        if not self._drag_ids or not self._ghost:
            return
        y, height = self._pointer.y(), self.viewport().height()
        direction = -1 if y < 36 else (1 if y > height - 36 else 0)
        if direction:
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() + direction * 12)
        target = min(max(0, y - self._ghost.height() / 2), max(0, height - self._ghost.height()))
        self._follow_y += (target - self._follow_y) * (.38 if motion_enabled(self) else 1)
        self._place_ghost()
        self._update_slot()

    def _update_slot(self):
        if not self._drag_ids:
            return
        row = self.rowAt(self._pointer.y())
        if row < 0:
            self._drag_slot = 0 if self._pointer.y() < 0 else self.rowCount()
        else:
            self._drag_slot = row + int(self._pointer.y() > self.row_rect(row).center().y())
        self.viewport().update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._pressed_handle:
            dragged = self._drag_ids[:]
            slot = self._drag_slot
            inside = self.viewport().rect().contains(event.position().toPoint())
            order = [self._uid(row) for row in range(self.rowCount())]
            anchor = next((uid for uid in order[slot:] if uid not in dragged), None) if slot is not None else None
            remaining = [uid for uid in order if uid not in dragged]
            at = remaining.index(anchor) if anchor else len(remaining)
            changed = remaining[:at] + dragged + remaining[at:] != order
            self.cancel_drag()
            if inside and dragged and slot is not None and changed:
                self.reorder_requested.emit(dragged, anchor)
            event.accept()
            return
        if self.management and event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.management:
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._pressed_handle:
            self.cancel_drag()
            return
        if self.management and event.key() == Qt.Key.Key_Space:
            uid = self._uid(self.currentRow())
            if uid:
                self.toggle_requested.emit(uid)
            return
        if self.management and event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.select_all_requested.emit()
            return
        super().keyPressEvent(event)

    def event(self, event):
        if hasattr(self, '_long_press') and event.type() in (QEvent.Type.WindowDeactivate, QEvent.Type.FocusOut,
                                                            QEvent.Type.EnabledChange):
            self.cancel_drag()
        return super().event(event)

    def cancel_drag(self):
        self._long_press.stop()
        self._drag_timer.stop()
        self._lift.stop()
        self._pressed_handle = None
        self._drag_ids = []
        self._drag_slot = None
        if self._ghost:
            self._ghost.hide()
            self._ghost.deleteLater()
            self._ghost = None
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.viewport().update()

    def leaveEvent(self, event):
        self.hovered_row = -1
        self.viewport().update()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        self.hovered_row = self.rowAt(pos.y()) if self.viewport().rect().contains(pos) else -1

    def hideEvent(self, event):
        self.cancel_drag()
        super().hideEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drag_slot is not None:
            y = self.rowViewportPosition(self._drag_slot) if self._drag_slot < self.rowCount() else (
                self.rowViewportPosition(self.rowCount() - 1) + self.rowHeight(self.rowCount() - 1))
            painter = QPainter(self.viewport())
            painter.setPen(QPen(QColor('#9281b8'), 3))
            painter.drawLine(8, y, self.viewport().width() - 8, y)
