"""A cancellable bulk-edit session; only Done persists its candidate linked list."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QCheckBox, QFileDialog, QToolButton,
                              QMenu, QMessageBox, QLayout)
from .management import ManagementSession
from .labels import record_labels
from .ui_expand import AnimatedExpansion
from .ui_labels import choose_labels
from .ui_widgets import label, button, friendly_error


class ListManagement:
    def build_management_bar(self):
        self._management_session = None
        self.management_bar = AnimatedExpansion()
        self.management_bar.setObjectName('managementBar')
        layout = QVBoxLayout(self.management_bar)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        selection = QHBoxLayout()
        self.select_all = QCheckBox('全选当前结果')
        self.select_all.setTristate(True)
        self.select_all.clicked.connect(self.toggle_all_friends)
        selection.addWidget(self.select_all)
        self.selection_count = label('', 'muted')
        selection.addWidget(self.selection_count, 1)
        self.management_done_button = button('完成', self.finish_management, True)
        selection.addWidget(self.management_done_button)
        layout.addLayout(selection)
        actions = QHBoxLayout()
        favorite = QToolButton()
        favorite.setText('收藏…')
        favorite.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(favorite)
        menu.addAction('加入收藏', lambda: self.apply_batch('favorite', True))
        menu.addAction('取消收藏', lambda: self.apply_batch('favorite', False))
        favorite.setMenu(menu)
        group = button('设置标签…', self.batch_group)
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
            if self.managing:
                self.cancel_management()
            else:
                self.request_leave(lambda: self.set_management(True))

    def friend_source(self):
        return self._management_session if self.managing and self._management_session else self.store

    def set_management(self, enabled):
        if enabled == self.managing:
            return
        self.table.cancel_drag()
        self._management_session = ManagementSession(self.store) if enabled else None
        self.managing = enabled
        self._checked_ids.clear()
        self._selected_id = None
        self.compact_detail = False
        self.management_bar.set_expanded(enabled)
        self.management_button.setVisible(self.page_name == '好友')
        self.management_button.setText('取消' if enabled else '☰ 管理列表')
        self.management_button.setToolTip('放弃本次管理中的所有修改' if enabled else '选择好友并批量操作，拖动调整顺序')
        self.add_button.setVisible(not enabled and self.page_name in ('好友', '概览'))
        self.refresh_groups()
        self.refresh_friends()

    def finish_management(self, after=None):
        # QPushButton.clicked may supply its checked flag.
        after = after if callable(after) else None
        session = self._management_session
        if not self.managing or not session or self._busy:
            return
        self.table.cancel_drag()
        if not session.dirty:
            self.set_management(False)
            if after:
                after()
            return
        def saved(_):
            self.set_management(False)
            self.notify('本次列表修改已保存。')
            if after:
                after()
        self.start_task('commit_management', (session.payload(), session.base_revision),
                        success=saved, text='正在保存本次列表修改…')

    def confirm_cancel_management(self):
        if self.settings.value('skip_management_cancel_warning', False, bool):
            return True
        box = QMessageBox(self)
        box.setWindowTitle('放弃本次列表修改？')
        box.setText('取消管理后，本次调整的顺序、收藏、标签和移入回收站操作都不会保留。')
        box.setInformativeText('如需保留，请返回并点击“完成”。')
        box.setStandardButtons(QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        box.button(QMessageBox.StandardButton.Discard).setText('放弃修改')
        box.button(QMessageBox.StandardButton.Cancel).setText('继续管理')
        checkbox = QCheckBox('知道，以后不再提示', box)
        box.setCheckBox(checkbox)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Discard:
            return False
        if checkbox.isChecked():
            self.settings.setValue('skip_management_cancel_warning', True)
            self.settings.sync()
        return True

    def cancel_management(self, after=None):
        if not self.managing or self._busy:
            return
        self.table.cancel_drag()
        if not self.confirm_cancel_management():
            return
        self.set_management(False)
        self.notify('已放弃本次列表修改。')
        if callable(after):
            after()

    def management_leave_choice(self):
        box = QMessageBox(self)
        box.setWindowTitle('列表修改尚未保存')
        box.setText('要保存本次列表管理中的修改吗？')
        box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                               QMessageBox.StandardButton.Cancel)
        for standard, text in [(QMessageBox.StandardButton.Save, '保存并继续'),
                               (QMessageBox.StandardButton.Discard, '放弃修改'),
                               (QMessageBox.StandardButton.Cancel, '继续管理')]:
            box.button(standard).setText(text)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec()

    def request_leave_management(self, action):
        if self._busy:
            return
        if not self.managing:
            action()
            return
        self.table.cancel_drag()
        if self._management_session.dirty:
            choice = self.management_leave_choice()
            if choice == QMessageBox.StandardButton.Save:
                self.finish_management(action)
                return
            if choice != QMessageBox.StandardButton.Discard:
                return
        self.set_management(False)
        action()

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
        try:
            count = self._management_session.batch_update(ids, action, value)
        except (ValueError, KeyError, OSError) as exc:
            self.notify(friendly_error(exc), True)
            return
        self.refresh_groups()
        self.refresh_friends()
        self.notify(f'已暂存 {count} 位好友的修改。点击“完成”保存，或“取消”放弃。')

    def batch_group(self):
        if self._busy or not self.selected_batch_ids():
            return
        source = self.friend_source()
        ids = self.selected_batch_ids()
        shared = set(record_labels(source.record(ids[0])))
        for uid in ids[1:]:
            shared.intersection_update(record_labels(source.record(uid)))
        selected = choose_labels(self, source.label_names(), sorted(shared), '设置所选好友的标签')
        if selected is not None:
            self.apply_batch('labels', selected)

    def batch_export(self):
        ids = self.selected_batch_ids()
        if self._busy or not ids:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出所选好友 · 保留原始相对顺序', '所选好友.json', '好友档案 (*.json)')
        if path:
            self.start_task('export_management_selected', (path, ids, self._management_session.payload()),
                            success=lambda count: self.notify(f'已导出 {count} 位好友，包含照片及全部资料。'), text='正在导出所选好友…')

    def reorder_friends(self, ids, anchor):
        if not self.managing or not self.can_reorder() or self._busy:
            return
        try:
            count = self._management_session.move_many(ids, anchor)
        except (ValueError, KeyError, OSError) as exc:
            self.notify(friendly_error(exc), True)
            return
        self.refresh_friends()
        self.notify(f'已暂存 {count} 位好友的顺序。点击“完成”保存，或“取消”放弃。')
