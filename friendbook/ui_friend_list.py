"""Row-level interaction and handle-only dragging; all mutations are UUID commands."""
from PySide6.QtCore import (Qt, QTimer, Signal, QPoint, QRect, QEasingCurve,
                           QVariantAnimation, QEvent, QElapsedTimer)
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
        if index.row() == view.hovered_row and not view._drag_ids:
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
        # Preview coordinates are independent of the model. UUIDs keep the rows
        # stable even when several, non-adjacent friends are lifted together.
        self._preview_rows = []
        self._dragged_set = set()
        self._remaining_rows = []
        self._remaining_tops = []
        self._row_positions = {}
        self._row_targets = {}
        self._row_velocity = {}
        self._row_heights = {}
        self._gap_index = None
        self._gap_height = 0
        self._returning = False
        self._frame_clock = QElapsedTimer()
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

    def preview_row_rect(self, row):
        """Visible row geometry while the unchanged model is being previewed."""
        uid = self._uid(row)
        if uid not in self._row_positions:
            return self.row_rect(row)
        return QRect(0, round(self._row_positions[uid]) - self.verticalScrollBar().value(),
                     self.viewport().width(), self._row_heights[uid])

    def _uid(self, row):
        item = self.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def mousePressEvent(self, event):
        if self._returning:
            self.cancel_drag()
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
        self._preview_rows = [(index, self._uid(index)) for index in range(self.rowCount())]
        self._dragged_set = set(self._drag_ids)
        self._remaining_rows = [(index, uid) for index, uid in self._preview_rows
                                if uid not in self._dragged_set]
        self._row_positions = {uid: float(self.verticalHeader().sectionPosition(index))
                               for index, uid in self._preview_rows}
        self._row_targets = self._row_positions.copy()
        self._row_velocity = {uid: 0.0 for _, uid in self._preview_rows}
        self._row_heights = {uid: self.rowHeight(index) for index, uid in self._preview_rows}
        self._remaining_tops = [0]
        for _, uid in self._remaining_rows:
            self._remaining_tops.append(self._remaining_tops[-1] + self._row_heights[uid])
        self._gap_height = sum(self._row_heights[uid] for uid in self._drag_ids)
        self._gap_index = sum(index < row for index, _ in self._remaining_rows)
        self._returning = False
        self._set_preview_targets()
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
        self._frame_clock.start()
        self._update_slot()

    def _place_ghost(self):
        if self._ghost:
            lift = self._lift.currentValue() or 0.0
            self._ghost.move(round(4 * lift), round(self._follow_y - 2 * lift))

    def _drag_frame(self):
        if not self._preview_rows:
            return
        elapsed = self._frame_clock.restart() / 1000 if self._frame_clock.isValid() else .016
        # A damped spring gives both opening and closing gaps a slight settling
        # motion. Clamp a busy event loop's step so rows never shoot off-screen.
        elapsed = min(.032, max(.001, elapsed))
        moving = False
        for _, uid in self._preview_rows:
            target = self._row_targets[uid]
            position, velocity = self._row_positions[uid], self._row_velocity[uid]
            if motion_enabled(self):
                velocity += ((target - position) * 300 - velocity * 28) * elapsed
                position += velocity * elapsed
                if abs(target - position) < .15 and abs(velocity) < .5:
                    position, velocity = target, 0.0
            else:
                position, velocity = target, 0.0
            self._row_positions[uid], self._row_velocity[uid] = position, velocity
            moving = moving or position != target
        self.viewport().update()
        if self._returning:
            if not moving:
                self._clear_preview()
                self._drag_timer.stop()
            return
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
        remaining = self._remaining_rows
        y = self._pointer.y() + self.verticalScrollBar().value()
        slot = self._gap_index
        # Compare with the rows bordering the current gap, never with their
        # transient spring positions. The gap itself is a stable drop region;
        # a stationary pointer cannot make neighboring rows oscillate.
        while slot < len(remaining):
            uid = remaining[slot][1]
            if y <= self._row_targets[uid] + self._row_heights[uid] / 2:
                break
            slot += 1
        while slot > 0:
            uid = remaining[slot - 1][1]
            # Compute the compact position: rows already passed by the first
            # loop have not received their new target until below.
            top = self._remaining_tops[slot - 1]
            if y >= top + self._row_heights[uid] / 2:
                break
            slot -= 1
        if slot != self._gap_index:
            self._gap_index = slot
            self._set_preview_targets()
        self._drag_slot = remaining[slot][0] if slot < len(remaining) else self.rowCount()
        self.viewport().update()

    def _set_preview_targets(self):
        top = 0
        for index, (_, uid) in enumerate(self._remaining_rows):
            if index == self._gap_index:
                top += self._gap_height
            self._row_targets[uid] = float(top)
            top += self._row_heights[uid]
        if not motion_enabled(self):
            self._row_positions.update(self._row_targets)
            self._row_velocity = dict.fromkeys(self._row_velocity, 0.0)

    def gap_rect(self):
        """The actual reserved insertion space, in viewport coordinates."""
        if self._gap_index is None:
            return QRect()
        top = self._remaining_tops[self._gap_index]
        return QRect(4, top - self.verticalScrollBar().value(),
                     max(0, self.viewport().width() - 8), self._gap_height)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._pressed_handle:
            dragged = self._drag_ids[:]
            slot = self._drag_slot
            inside = self.viewport().rect().contains(event.position().toPoint())
            order = [self._uid(row) for row in range(self.rowCount())]
            anchor = next((uid for uid in order[slot:] if uid not in dragged), None) if slot is not None else None
            remaining = [uid for uid in order if uid not in dragged]
            at = remaining.index(anchor) if anchor else len(remaining)
            changed = (remaining[:at] + dragged + remaining[at:] != order
                       and (event.position().toPoint() - self._press_pos).manhattanLength() >= 8)
            self.cancel_drag(animate=not (inside and changed))
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
            self.cancel_drag(animate=True)
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

    def cancel_drag(self, animate=False):
        self._long_press.stop()
        self._lift.stop()
        returning = bool(animate and self._drag_ids and motion_enabled(self) and self.isVisible())
        if returning:
            top = self.gap_rect().top() + self.verticalScrollBar().value()
            for uid in self._drag_ids:
                self._row_positions[uid] = float(top)
                top += self._row_heights[uid]
            self._row_targets = {uid: float(self.verticalHeader().sectionPosition(row))
                                 for row, uid in self._preview_rows}
        self._pressed_handle = None
        self._drag_ids = []
        self._drag_slot = None
        self._gap_index = None
        if self._ghost:
            self._ghost.hide()
            self._ghost.deleteLater()
            self._ghost = None
        if returning:
            self._returning = True
            self._frame_clock.start()
            self._drag_timer.start()
        else:
            self._drag_timer.stop()
            self._clear_preview()
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.viewport().update()

    def _clear_preview(self):
        self._preview_rows = []
        self._dragged_set.clear()
        self._remaining_rows = []
        self._remaining_tops = []
        self._row_positions.clear()
        self._row_targets.clear()
        self._row_velocity.clear()
        self._row_heights.clear()
        self._gap_index = None
        self._gap_height = 0
        self._returning = False
        self.viewport().update()

    def leaveEvent(self, event):
        self.hovered_row = -1
        self.viewport().update()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._ghost:
            self._ghost.resize(max(0, self.viewport().width() - 8), self._ghost.height())
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        self.hovered_row = self.rowAt(pos.y()) if self.viewport().rect().contains(pos) else -1

    def hideEvent(self, event):
        self.cancel_drag()
        super().hideEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._preview_rows:
            return
        painter = QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), self.viewport().palette().base())
        gap = self.gap_rect().adjusted(0, 3, 0, -3)
        if not gap.isEmpty():
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor('#9281b8'), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(146, 129, 184, 20))
            painter.drawRoundedRect(gap, 6, 6)
        offset = self.verticalScrollBar().value()
        for row, uid in self._preview_rows:
            if uid in self._dragged_set and not self._returning:
                continue
            top, height = round(self._row_positions[uid]) - offset, self._row_heights[uid]
            if top + height < 0 or top > self.viewport().height():
                continue
            painter.fillRect(QRect(0, top, self.viewport().width(), height),
                             self.viewport().palette().base())
            for column in range(self.columnCount()):
                option = QStyleOptionViewItem()
                self.initViewItemOption(option)
                option.rect = QRect(self.columnViewportPosition(column), top,
                                    self.columnWidth(column), height)
                self.itemDelegate().paint(painter, option, self.model().index(row, column))
