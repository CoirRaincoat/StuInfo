"""Searchable multi-select labels shared by individual and bulk editing."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QLabel, QDialog, QDialogButtonBox)


class TagPicker(QWidget):
    changed = Signal()

    def __init__(self, available=(), selected=(), parent=None):
        super().__init__(parent)
        self._selected = list(dict.fromkeys(selected))
        self._available = sorted(set(available) | set(selected), key=str.casefold)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.toggle = QPushButton()
        self.toggle.setCheckable(True)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setAccessibleName('展开或收起标签选择')
        layout.addWidget(self.toggle)
        self.panel = QWidget()
        body = QVBoxLayout(self.panel)
        body.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('检索标签，或输入名称新建')
        self.search.setMaxLength(200)
        self.search.setClearButtonEnabled(True)
        row.addWidget(self.search, 1)
        self.create_button = QPushButton('＋ 新建标签')
        self.create_button.setAutoDefault(False)
        row.addWidget(self.create_button)
        body.addLayout(row)
        self.options = QListWidget()
        self.options.setMinimumHeight(100)
        self.options.setMaximumHeight(180)
        self.options.setAccessibleName('可多选的标签列表')
        body.addWidget(self.options)
        self.empty = QLabel('没有匹配的标签，可新建后勾选。')
        body.addWidget(self.empty)
        layout.addWidget(self.panel)
        self.panel.hide()
        self.toggle.toggled.connect(self.panel.setVisible)
        self.toggle.toggled.connect(self._caption)
        self.search.textChanged.connect(self._populate)
        self.search.returnPressed.connect(self.create_label)
        self.create_button.clicked.connect(self.create_label)
        self.options.itemChanged.connect(self._check)
        self._populate()
        self._caption()

    def _caption(self, *_):
        names = '、'.join(self._selected)
        caption = names if len(names) <= 38 else names[:35] + '…'
        self.toggle.setText((caption or '选择标签（可多选）') + ('  ▴' if self.toggle.isChecked() else '  ▾'))
        self.toggle.setToolTip(names or '选择已有标签，或新建标签')

    def _populate(self, *_):
        query = self.search.text().strip().casefold()
        self.options.blockSignals(True)
        self.options.clear()
        for name in self._available:
            if query in name.casefold():
                item = QListWidgetItem(name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if name in self._selected else Qt.CheckState.Unchecked)
                self.options.addItem(item)
        self.options.blockSignals(False)
        self.empty.setVisible(not self.options.count())
        self.create_button.setEnabled(bool(self.search.text().strip()) and self.search.text().strip() not in self._available)

    def _check(self, item):
        name = item.text()
        if item.checkState() == Qt.CheckState.Checked and name not in self._selected:
            self._selected.append(name)
        elif item.checkState() != Qt.CheckState.Checked and name in self._selected:
            self._selected.remove(name)
        self._caption()
        self.changed.emit()

    def create_label(self):
        name = self.search.text().strip()
        if not name:
            return
        if name not in self._available:
            self._available.append(name)
            self._available.sort(key=str.casefold)
        if name not in self._selected:
            self._selected.append(name)
        self.search.clear()
        self._populate()
        self._caption()
        self.changed.emit()

    def selected_labels(self):
        return list(self._selected)


def choose_labels(parent, available, selected=(), title='设置标签'):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(460, 350)
    layout = QVBoxLayout(dialog)
    hint = QLabel('可选择多个标签；清空选择表示不设置标签。')
    hint.setWordWrap(True)
    layout.addWidget(hint)
    picker = TagPicker(available, selected, dialog)
    picker.toggle.setChecked(True)
    layout.addWidget(picker)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText('应用')
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    return picker.selected_labels() if dialog.exec() == QDialog.DialogCode.Accepted else None
