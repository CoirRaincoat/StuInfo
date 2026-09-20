"""Bulk-list mode: selection is a set of stable IDs, scoped to visible results."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QInputDialog, QFileDialog, QToolButton, QMenu
from .ui_widgets import label, button


class ListManagement:
    def build_management_bar(self):
        self.management_bar = QWidget()
        self.management_bar.setObjectName('managementBar')
        layout = QVBoxLayout(self.management_bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        selection = QHBoxLayout()
        self.select_all = QCheckBox('全选当前结果')
        self.select_all.setTristate(True)
        self.select_all.clicked.connect(self.toggle_all_friends)
        selection.addWidget(self.select_all)
        self.selection_count = label('', 'muted')
        selection.addWidget(self.selection_count, 1)
        selection.addWidget(button('完成', lambda: self.set_management(False), True))
        layout.addLayout(selection)
        actions = QHBoxLayout()
        favorite = QToolButton()
        favorite.setText('收藏…')
        favorite.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(favorite)
        menu.addAction('加入收藏', lambda: self.apply_batch('favorite', True))
        menu.addAction('取消收藏', lambda: self.apply_batch('favorite', False))
        favorite.setMenu(menu)
        group = button('移至分组…', self.batch_group)
        export = button('导出所选…', self.batch_export)
        delete = button('移入回收站', lambda: self.apply_batch('delete'))
        self.batch_buttons = (favorite, group, export, delete)
        for control in self.batch_buttons:
            actions.addWidget(control)
        actions.addStretch()
        layout.addLayout(actions)
        self.management_bar.hide()
        return self.management_bar

    def toggle_management(self):
        if self.page_name == '好友' and not self._busy:
            self.request_leave(lambda: self.set_management(not self.managing))

    def set_management(self, enabled):
        self.managing = enabled
        self._checked_ids.clear()
        self._selected_id = None
        self.compact_detail = False
        self.management_bar.setVisible(enabled)
        self.management_button.setVisible(not enabled and self.page_name == '好友')
        self.add_button.setVisible(not enabled and self.page_name in ('好友', '概览'))
        self.refresh_friends()

    def toggle_friend_check(self, uid):
        if not self.managing or self._busy or uid not in {r['id'] for r in self._visible_records}:
            return
        if uid in self._checked_ids:
            self._checked_ids.remove(uid)
        else:
            self._checked_ids.add(uid)
        self.update_management_selection()

    def toggle_all_friends(self, *_):
        if not self.managing or self._busy:
            return
        visible = {r['id'] for r in self._visible_records}
        self._checked_ids = set() if self._checked_ids == visible else visible
        self.update_management_selection()

    def update_management_selection(self):
        visible = {r['id'] for r in self._visible_records}
        self._checked_ids.intersection_update(visible)
        self.table.checked_ids = set(self._checked_ids)
        self.table.blockSignals(True)
        if self.managing:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in self._checked_ids
                                   else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        count = len(self._checked_ids)
        self.select_all.blockSignals(True)
        self.select_all.setCheckState(Qt.CheckState.Checked if count and count == len(visible) else (
            Qt.CheckState.PartiallyChecked if count else Qt.CheckState.Unchecked))
        self.select_all.blockSignals(False)
        self.select_all.setEnabled(bool(visible))
        self.selection_count.setText(f'已选 {count} / {len(visible)} 位')
        for control in self.batch_buttons:
            control.setEnabled(bool(count))
        self.table.viewport().update()

    def selected_batch_ids(self):
        return [r['id'] for r in self._visible_records if r['id'] in self._checked_ids]

    def apply_batch(self, action, value=None):
        ids = self.selected_batch_ids()
        if not self.managing or not ids or self._busy:
            return
        if action == 'delete' and not self.confirm('批量移入回收站', f'将所选 {len(ids)} 位好友移入回收站？可以逐个还原。未选好友不会改变。'):
            return
        self.start_task('batch_update', (ids, action, value),
                        success=lambda count: self.notify(f'已处理 {count} 位好友。' + ('可在回收站还原。' if action == 'delete' else '')),
                        text=f'正在处理 {len(ids)} 位好友…')

    def batch_group(self):
        if self._busy or not self.selected_batch_ids():
            return
        name, accepted = QInputDialog.getText(self, '批量设置分组', '分组名称（留空表示未分组）：')
        if accepted:
            self.apply_batch('group', name)

    def batch_export(self):
        ids = self.selected_batch_ids()
        if self._busy or not ids:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出所选好友 · 保留原始相对顺序', '所选好友.json', '好友档案 (*.json)')
        if path:
            self.start_task('export_selected', (path, ids),
                            success=lambda count: self.notify(f'已导出 {count} 位好友，包含照片及全部资料。'), text='正在导出所选好友…')

    def reorder_friends(self, ids, anchor):
        if not self.managing or not self.can_reorder() or self._busy:
            return
        self.start_task('move_many', (ids, anchor),
                        success=lambda count: self.notify(f'已移动 {count} 位好友，原始顺序已保存。'), text='正在保存列表顺序…')
