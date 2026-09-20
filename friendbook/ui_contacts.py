"""Grouped contact editor without changing the persistent contacts mapping."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit
from .contact_fields import CONTACT_KINDS, grouped_contacts, contact_caption
from .ui_widgets import label, button, card, scroll_content


class ContactEditor(QWidget):
    def __init__(self, values, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll, content = scroll_content()
        layout.addWidget(scroll)
        content.addWidget(label('每类可添加多项；只有一项时不编号。旧标签原样保留，其他渠道可自定义。', 'muted', True))
        self.rows = {kind: [] for kind in CONTACT_KINDS}
        self.sections = {}
        for kind in CONTACT_KINDS:
            frame, section = card(kind)
            self.sections[kind] = QVBoxLayout()
            self.sections[kind].setSpacing(8)
            section.addLayout(self.sections[kind])
            add = button('＋ 添加' + ('渠道' if kind == '其他' else kind),
                         lambda checked=False, k=kind: self.add_entry(k))
            section.addWidget(add)
            content.addWidget(frame)
        for kind, entries in grouped_contacts(values).items():
            for name, value in entries:
                self.add_entry(kind, value, name, focus=False)
        content.addStretch()

    def add_entry(self, kind, value='', original='', focus=True):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        caption = QLineEdit(original) if kind == '其他' else label('')
        if kind == '其他':
            caption.setPlaceholderText('渠道名称')
            caption.setMaximumWidth(115)
        else:
            caption.setMinimumWidth(44)
            caption.setMaximumWidth(94)
            caption.setWordWrap(True)
        field = QLineEdit(value)
        field.setPlaceholderText({'电话': '电话号码', 'QQ': 'QQ 号码', '微信': '微信号',
                                  '邮箱': '邮箱地址', '其他': '内容'}[kind])
        layout.addWidget(caption)
        layout.addWidget(field, 1)
        entry = dict(widget=row, caption=caption, field=field, original=original)
        remove = button('−', lambda: self.remove_entry(kind, entry))
        remove.setAccessibleName('移除此项' + kind)
        remove.setToolTip('移除此项' + kind)
        layout.addWidget(remove)
        self.rows[kind].append(entry)
        self.sections[kind].addWidget(row)
        self._captions(kind)
        if focus:
            field.setFocus()
        return field

    def remove_entry(self, kind, entry):
        self.rows[kind].remove(entry)
        self.sections[kind].removeWidget(entry['widget'])
        entry['widget'].deleteLater()
        self._captions(kind)

    def _captions(self, kind):
        if kind != '其他':
            for index, entry in enumerate(self.rows[kind]):
                caption = contact_caption(kind, index, len(self.rows[kind]), entry['original'])
                entry['caption'].setText(caption)
                entry['field'].setAccessibleName(caption)

    def values(self):
        result, new = {}, []
        counts = {kind: sum(bool(row['original'] or row['field'].text().strip()) for row in rows)
                  for kind, rows in self.rows.items()}
        for kind, rows in self.rows.items():
            for entry in rows:
                name = entry['caption'].text().strip() if kind == '其他' else entry['original']
                value = entry['field'].text()
                if kind != '其他' and not name:
                    if value.strip():
                        new.append((kind, value))
                    continue
                if not name and not value.strip():
                    continue
                if not name or name in result:
                    raise ValueError('联系方式名称不能为空或重复，请检查“其他”渠道名称')
                result[name] = value
        # Reserve every existing key first. Adding a new phone never overwrites a legacy 电话1.
        for kind, value in new:
            name, index = (kind if counts[kind] == 1 else kind + '1'), 1
            while name in result:
                index += 1
                name = kind + str(index)
            result[name] = value
        return result
