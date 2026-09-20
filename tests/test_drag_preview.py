"""Exercise drag preview geometry without committing or replacing model rows."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
import pytest
from PySide6.QtCore import Qt, QPoint, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTableWidgetItem
from friendbook.ui_friend_list import FriendsTable


def until(predicate):
    deadline = time.monotonic() + 3
    while not predicate():
        assert time.monotonic() < deadline, 'Drag preview did not reach its expected state'
        QTest.qWait(10)


@pytest.fixture
def table():
    app = QApplication.instance() or QApplication([])
    widget = FriendsTable()
    widget.setProperty('reduceMotion', True)
    widget.configure_management(True, [], True)
    widget.setRowCount(10)
    for row in range(10):
        widget.setRowHeight(row, 46)
        for column in range(5):
            item = QTableWidgetItem(f'Friend {row}' if column == 0 else '')
            item.setData(Qt.ItemDataRole.UserRole, str(row))
            widget.setItem(row, column, item)
    for column in range(5):
        widget.setColumnWidth(column, 110 if column < 4 else 40)
    widget.resize(540, 460)
    widget.show()
    app.processEvents()
    yield widget
    widget.cancel_drag()
    widget.close()
    widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def lift(table, row=0):
    point = table.visualItemRect(table.item(row, 4)).center()
    QTest.mousePress(table.viewport(), Qt.MouseButton.LeftButton, pos=point)
    until(lambda: bool(table._drag_ids))
    return point


def test_handle_drag_reserves_full_gap_and_preserves_multiple_uuid_order(table):
    table.checked_ids = {'2', '0'}
    signals = []
    table.reorder_requested.connect(lambda ids, anchor: signals.append((ids, anchor)))
    start = lift(table)
    end = QPoint(start.x(), table.row_rect(5).bottom() - 2)
    QTest.mouseMove(table.viewport(), end)
    assert table._drag_ids == ['0', '2']
    assert table.gap_rect().height() == 92
    assert table._gap_index == 4
    assert table.gap_rect().top() == 184
    assert table._row_positions['5'] + 46 == table.gap_rect().top()
    assert table._row_positions['6'] == table.gap_rect().bottom() + 1
    # No placeholder rows or model mutation can change identity during preview.
    assert [table._uid(row) for row in range(table.rowCount())] == list(map(str, range(10)))
    QTest.mouseRelease(table.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert signals == [(['0', '2'], '6')]
    assert table.gap_rect().isEmpty() and not table._preview_rows
    assert not table._drag_timer.isActive()


def test_handle_drag_neighbors_spring_open_and_back_on_escape(table):
    table.setProperty('reduceMotion', False)
    signals = []
    table.reorder_requested.connect(lambda *args: signals.append(args))
    start = lift(table)
    end = QPoint(start.x(), table.row_rect(3).bottom() - 2)
    QTest.mouseMove(table.viewport(), end)
    assert table._row_targets['1'] == 0
    until(lambda: 0 < table._row_positions['1'] < 46)
    assert table.gap_rect().height() == 46
    QTest.keyClick(table, Qt.Key.Key_Escape)
    assert not table._drag_ids and table.gap_rect().isEmpty()
    assert table._returning and table._row_targets['1'] == 46
    until(lambda: not table._returning)
    assert not table._preview_rows and not table._drag_timer.isActive()
    assert not signals


def test_handle_drag_gap_does_not_jump_under_stationary_pointer(table):
    start = lift(table)
    end = QPoint(start.x(), table.row_rect(3).bottom() - 2)
    QTest.mouseMove(table.viewport(), end)
    expected = (table._drag_slot, table.gap_rect())
    for _ in range(20):
        table._drag_frame()
    assert (table._drag_slot, table.gap_rect()) == expected
    QTest.keyClick(table, Qt.Key.Key_Escape)
    assert not table._preview_rows and not table._returning


def test_handle_drag_releasing_stationary_multiselection_keeps_original_order(table):
    table.checked_ids = {'0', '2'}
    signals = []
    table.reorder_requested.connect(lambda *args: signals.append(args))
    start = lift(table, row=2)
    QTest.mouseRelease(table.viewport(), Qt.MouseButton.LeftButton, pos=start)
    assert not signals
    assert not table._preview_rows


def test_pending_long_press_normal_mode_has_no_drag_preview(table):
    table.configure_management(False, [], False)
    point = table.visualItemRect(table.item(0, 3)).center()
    QTest.mousePress(table.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseMove(table.viewport(), point + QPoint(0, 60))
    assert not table._long_press.isActive()
    assert not table._drag_ids and table.gap_rect().isEmpty()
    QTest.mouseRelease(table.viewport(), Qt.MouseButton.LeftButton, pos=point + QPoint(0, 60))
