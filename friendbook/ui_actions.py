"""Discoverable data and merge actions shared by the main workspace pages."""
import base64
import copy
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QDialogButtonBox, QFileDialog, QInputDialog, QLabel)
from .ui_widgets import label, configure_table
from .labels import record_labels, with_labels


class DataActions:
    def merge(self):
        if self.selected():
            self.request_leave(self._begin_merge)

    def _begin_merge(self):
        uid = self.selected()
        if not uid:
            return
        keep = self.store.record(uid)
        matches = self.store.duplicate_records(keep)
        if not matches:
            self.notify('未发现同名或联系方式完全相同的其他档案。')
            return
        names = [f"{r['name'] or '未命名好友'} · {' / '.join(record_labels(r)) or '未设置标签'} · {r['id']}" for r in matches]
        selected, ok = QInputDialog.getItem(self, '选择合并来源', '保留当前好友，选择另一份疑似重复档案：', names, editable=False)
        if not ok:
            return
        source = matches[names.index(selected)]
        merged = copy.deepcopy(keep)
        for key in ('birth', 'interests', 'photo'):
            merged[key] = keep[key] or source[key]
        merged = with_labels(merged, record_labels(keep) + record_labels(source))
        merged['tags'] = list(dict.fromkeys(keep['tags'] + source['tags']))
        merged['favorite'] = keep['favorite'] or source['favorite']
        merged['notes'] = keep['notes'] + '\n\n[合入档案备注]\n' + source['notes']
        for key in ('contacts', 'custom'):
            for name, value in source[key].items():
                destination = name
                while destination in merged[key] and merged[key][destination] != value:
                    destination += '（合入）'
                merged[key][destination] = value
        conflicts = [k for k in ('name', 'birth', 'interests', 'photo')
                     if keep[k] and source[k] and keep[k] != source[k]]
        if conflicts:
            dialog = QDialog(self)
            dialog.setWindowTitle('检查合并冲突')
            dialog.resize(740, 430)
            layout = QVBoxLayout(dialog)
            layout.addWidget(label('选择要采用的内容，再到右侧面板检查完整草稿。\n点击保存后才合并，来源档案会保留在回收站。', 'muted', True))
            table = QTableWidget(len(conflicts), 4)
            configure_table(table)
            table.setHorizontalHeaderLabels(['字段', '当前好友', '合入来源', '采用'])
            names = dict(name='姓名', birth='出生信息', interests='兴趣', group='分组', photo='照片')
            choices = {}
            for row, key in enumerate(conflicts):
                table.setItem(row, 0, QTableWidgetItem(names[key]))
                for column, record in ((1, keep), (2, source)):
                    if key == 'photo':
                        photo = QLabel()
                        pix = QPixmap()
                        pix.loadFromData(base64.b64decode(record[key]))
                        photo.setPixmap(pix.scaled(70, 70, Qt.AspectRatioMode.KeepAspectRatio))
                        table.setCellWidget(row, column, photo)
                        table.setRowHeight(row, 80)
                    else:
                        item = QTableWidgetItem(record[key])
                        item.setToolTip(record[key])
                        table.setItem(row, column, item)
                combo = QComboBox()
                combo.addItems(['当前好友', '合入来源'])
                table.setCellWidget(row, 3, combo)
                choices[key] = combo
            layout.addWidget(table)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText('检查完整草稿')
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            for key, combo in choices.items():
                merged[key] = (source if combo.currentIndex() else keep)[key]
        self.open_editor(merged, '检查合并草稿', expected=keep['version'], source=source['id'])
        self.notify('正在检查合并草稿。保存后来源档案移入回收站，当前好友的位置保持不变。')

    def import_data(self):
        self.request_leave(self._choose_import)

    def _choose_import(self):
        path, _ = QFileDialog.getOpenFileName(self, '导入好友 JSON', '', '好友档案 (*.json)')
        if path:
            self.start_task('preview_import', (path,), success=self._confirm_import, text='正在校验导入文件…')

    def _confirm_import(self, preview):
        if self.confirm('导入好友', f"文件中有 {preview['total']} 份有效档案；{preview['skipped']} 个已存在 ID 将跳过。\n新档案追加到末尾，同名但不同 ID 的资料保持独立。现有档案不会被替换。"):
            self.start_task('import_prepared', (preview['records'], preview.get('label_catalog', [])),
                            success=lambda result: self.notify(f'导入完成：新增 {result[0]} 份，跳过 {result[1]} 份。'),
                            text='正在导入好友…')

    def export_data(self, backup=False):
        def choose():
            path, _ = QFileDialog.getSaveFileName(self, '完整备份' if backup else '导出全部有效好友',
                '好友档案备份.json' if backup else '好友档案.json', '好友档案 (*.json)')
            if path:
                self.start_task('export', (path, backup),
                                success=lambda _: self.notify('完整备份已保存。' if backup else '已导出全部有效好友，包含照片和自定义属性。'),
                                text='正在写入文件…')
        self.request_leave(choose)

    def backup(self):
        self.export_data(True)

    def recover(self):
        def choose():
            path, _ = QFileDialog.getOpenFileName(self, '选择完整备份', '', '好友档案 (*.json)')
            if path and self.confirm('恢复整个数据集', '这将替换所有有效好友、顺序和回收站。\n会先在数据目录保存恢复前完整备份；备份失败则不恢复。\n确定继续？'):
                self.start_task('recover', (path,), success=lambda safety: self.notify('恢复完成。恢复前备份已保存在数据目录。'), text='正在校验、备份并恢复数据…')
        self.request_leave(choose)

    def rename_group(self, group):
        def choose():
            name, ok = QInputDialog.getText(self, '修改标签名称', '新名称（留空表示移除此标签）：', text=group)
            if not ok or name.strip() == group:
                return
            destination = name.strip()
            if destination in self.store.group_counts() and not self.confirm('合并到已有标签', '目标标签已存在。好友将改用目标标签，其它标签保留，继续？'):
                return
            self.start_task('rename_group', (group, destination), success=lambda count: self.notify(f'已更新 {count} 位好友的标签。'), text='正在更新标签…')
        self.request_leave(choose)

    def dissolve_group(self, group):
        if self.confirm('移除标签', '将从所有好友中移除此标签，其它标签和好友资料都会保留。继续？'):
            self.start_task('rename_group', (group, ''), success=lambda count: self.notify(f'已从 {count} 位好友中移除此标签。'), text='正在更新标签…')
