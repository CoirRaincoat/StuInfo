"""Shared Qt components. Record validation remains in the business layer."""
import base64
import copy
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QIcon, QPalette, QPen, QGuiApplication
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame,
    QPushButton, QLineEdit, QPlainTextEdit, QCheckBox, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea, QAbstractItemView, QSizePolicy)
from .core import validate_record, photo_bytes
from .contact_fields import PROFILE_FIELDS
from .ui_motion import AnimatedTabs


def label(text, role='', wrap=False):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setObjectName(role)
    item.setWordWrap(wrap)
    if wrap:
        item.setMinimumWidth(0)
        item.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return item


def button(text, callback, primary=False):
    item = QPushButton(text)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    item.setObjectName('primary' if primary else 'button')
    item.clicked.connect(callback)
    return item


def card(title='', subtitle=''):
    frame = QFrame()
    frame.setObjectName('card')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    if title:
        layout.addWidget(label(title, 'sectionTitle'))
    if subtitle:
        layout.addWidget(label(subtitle, 'muted', True))
    return frame, layout


def scroll_content():
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 8, 0)
    layout.setSpacing(16)
    scroll.setWidget(content)
    return scroll, layout


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


def configure_table(table):
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(48)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setMinimumSectionSize(75)
    table.setAlternatingRowColors(False)


def _photo_pixmap(record):
    pixmap = QPixmap()
    encoded = (record or {}).get('photo')
    if encoded:
        try:
            pixmap.loadFromData(base64.b64decode(encoded))
        except (ValueError, TypeError):
            pass
    return pixmap


def _paint_avatar(painter, rect, pixmap, circular=False):
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    shape = QPainterPath()
    if circular:
        shape.addEllipse(rect)
    else:
        radius = min(16.0, rect.width() * .22)
        shape.addRoundedRect(rect, radius, radius)
    painter.fillPath(shape, QColor('#ddd8ec'))
    painter.save()
    painter.setClipPath(shape)
    if not pixmap.isNull():
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scale = max(rect.width() / pixmap.width(), rect.height() / pixmap.height())
        width, height = rect.width() / scale, rect.height() / scale
        source = QRectF((pixmap.width() - width) / 2, (pixmap.height() - height) / 2, width, height)
        painter.drawPixmap(rect, pixmap, source)
    else:
        # A neutral person silhouette is the default avatar; no missing data is invented.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#8f80ad'))
        size = min(rect.width(), rect.height())
        head = QRectF(rect.center().x() - size * .16, rect.y() + size * .18,
                      size * .32, size * .32)
        shoulders = QRectF(rect.center().x() - size * .32, rect.y() + size * .56,
                           size * .64, size * .48)
        painter.drawEllipse(head)
        painter.drawRoundedRect(shoulders, size * .18, size * .18)
    painter.restore()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor('#b7aec9'), max(1.0, min(rect.width(), rect.height()) * .035)))
    painter.drawPath(shape)


def avatar_icon(record, size=36):
    ratio = max(1.0, QGuiApplication.instance().devicePixelRatio())
    canvas = QPixmap(round(size * ratio), round(size * ratio))
    canvas.setDevicePixelRatio(ratio)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    margin = max(1.0, size * .04)
    _paint_avatar(painter, QRectF(margin, margin, size - 2 * margin, size - 2 * margin),
                  _photo_pixmap(record), circular=True)
    painter.end()
    return QIcon(canvas)


class Avatar(QWidget):
    def __init__(self, record=None, size=72, circular=False):
        super().__init__()
        self.setFixedSize(size, size)
        self.record = record or {}
        self.circular = circular
        self.pixmap = _photo_pixmap(self.record)

    def paintEvent(self, event):
        painter = QPainter(self)
        margin = max(1.0, self.width() * .025)
        _paint_avatar(painter, QRectF(margin, margin, self.width() - 2 * margin,
                                      self.height() - 2 * margin), self.pixmap, self.circular)


class Pairs(QWidget):
    def __init__(self, values, hint, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(label(hint, 'muted', True))
        self.table = QTableWidget(0, 2)
        configure_table(self.table)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.setHorizontalHeaderLabels(['名称 / 类型', '内容'])
        layout.addWidget(self.table, 1)
        for key, value in values.items():
            self.add(key, value)
        actions = QHBoxLayout()
        actions.addWidget(button('＋ 添加', lambda: self.add()))
        self.remove_button = button('移除选中项', self.remove)
        actions.addWidget(self.remove_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.table.itemSelectionChanged.connect(lambda: self.remove_button.setEnabled(self.table.currentRow() >= 0))
        self.remove_button.setEnabled(self.table.currentRow() >= 0)

    def add(self, key='', value=''):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(key))
        self.table.setItem(row, 1, QTableWidgetItem(value))
        self.table.setCurrentCell(row, 0)

    def remove(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def values(self):
        result = {}
        for row in range(self.table.rowCount()):
            key, value = (self.table.item(row, col).text().strip() for col in (0, 1))
            if not key and not value:
                continue
            if not key or key in result:
                raise ValueError('属性名称不能为空或重复。多个号码可分别命名为“手机”“工作电话”。')
            result[key] = value
        return result


class Editor(QWidget):
    save_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, record, title='编辑好友', parent=None):
        super().__init__(parent)
        from .ui_contacts import ContactEditor
        self.original = copy.deepcopy(record)
        self.photo = record['photo']
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(label(title, 'panelTitle'))
        layout.addWidget(label('保存后生效 · 未知信息可留空', 'muted'))
        self.tabs = AnimatedTabs()
        layout.addWidget(self.tabs, 1)
        scroll, basic = scroll_content()
        scroll.widget().setObjectName('panelContent')
        self.fields = {}
        basic.setContentsMargins(2, 16, 10, 8)
        photo_row = QHBoxLayout()
        self.photo_holder = QVBoxLayout()
        self.update_photo()
        photo_row.addLayout(self.photo_holder)
        actions = QVBoxLayout()
        actions.addWidget(button('选择照片', self.choose_photo))
        actions.addWidget(button('移除照片', self.clear_photo))
        photo_row.addLayout(actions)
        photo_row.addStretch()
        basic.addLayout(photo_row)
        for key, title_, placeholder in [('name', '姓名', '未填写时显示“未命名好友”'),
                ('birth', '出生信息', 'YYYY 或 YYYY-MM，未知留空'),
                ('group', '分组', '输入自定义分组，如同学、同事'),
                ('interests', '兴趣', '阅读、摄影、徒步……'), ('tags', '标签', '使用逗号分隔，如校园, 摄影')]:
            box = QVBoxLayout()
            box.setSpacing(5)
            box.addWidget(label(title_, 'fieldLabel'))
            field = QLineEdit(', '.join(record[key]) if key == 'tags' else record[key])
            field.setPlaceholderText(placeholder)
            self.fields[key] = field
            box.addWidget(field)
            basic.addLayout(box)
        self.favorite = QCheckBox('加入收藏')
        self.favorite.setChecked(record['favorite'])
        basic.addWidget(self.favorite)
        self.profile_fields = {}
        extra = QWidget()
        extra_layout = QVBoxLayout(extra)
        extra_layout.setContentsMargins(0, 4, 0, 0)
        for name in PROFILE_FIELDS:
            extra_layout.addWidget(label(name, 'fieldLabel'))
            field = QLineEdit(record['custom'].get(name, ''))
            field.setPlaceholderText('未知可留空')
            self.profile_fields[name] = field
            extra_layout.addWidget(field)
        expand = button('更多资料 · 籍贯等', lambda: None)
        expand.setToolTip('籍贯、现居地、学校 / 单位、职业')
        expand.setCheckable(True)
        expand.setChecked(any(name in record['custom'] for name in PROFILE_FIELDS))
        extra.setVisible(expand.isChecked())
        expand.toggled.connect(extra.setVisible)
        basic.addWidget(expand)
        basic.addWidget(extra)
        basic.addStretch()
        self.tabs.addTab(scroll, '资料')
        self.contacts = ContactEditor(record['contacts'])
        self.tabs.addTab(self.contacts, '联系方式')
        self.custom = Pairs({k: v for k, v in record['custom'].items() if k not in PROFILE_FIELDS},
                            '自由添加属性，例如相识地点、喜欢的颜色。籍贯等常用资料在“资料”页编辑。')
        self.tabs.addTab(self.custom, '自定义')
        self.notes = QPlainTextEdit(record['notes'])
        self.notes.setPlaceholderText('记录近况、相识故事，或下次见面想聊的事情……')
        self.tabs.addTab(self.notes, '备注')
        self.error = label('', 'error', True)
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        self.cancel_button = button('取消编辑', self.cancel_requested.emit)
        self.save_button = button('保存好友', self.save_requested.emit, True)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        self.initial = self.data()

    def update_photo(self):
        clear_layout(self.photo_holder)
        self.photo_holder.addWidget(Avatar(dict(name=self.original['name'], photo=self.photo)))

    def clear_photo(self):
        self.photo = ''
        self.update_photo()

    def choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择照片', '', '图片 (*.png *.jpg *.jpeg *.webp *.bmp)')
        if path:
            try:
                if Path(path).stat().st_size > 15 * 1024 * 1024:
                    raise ValueError('照片不能超过 15 MB')
                self.photo = photo_bytes(Path(path).read_bytes())
                self.update_photo()
                self.error.hide()
            except Exception as exc:
                self.show_error(friendly_error(exc))

    def data(self):
        record = copy.deepcopy(self.original)
        for key, field in self.fields.items():
            record[key] = field.text().strip()
        record['tags'] = [t.strip() for t in record['tags'].replace('，', ',').split(',') if t.strip()]
        custom = self.custom.values()
        for name, field in self.profile_fields.items():
            if name in custom:
                raise ValueError(f'“{name}”请在资料页填写，不能重复添加为自定义属性')
            value = field.text()
            if value or name in self.original['custom']:
                custom[name] = value
        record.update(contacts=self.contacts.values(), custom=custom,
                      notes=self.notes.toPlainText(), favorite=self.favorite.isChecked(), photo=self.photo)
        return record

    def validated(self):
        return validate_record(self.data())

    def dirty(self):
        try:
            return self.data() != self.initial
        except ValueError:
            return True

    def show_error(self, text):
        self.error.setText('未保存：' + text)
        self.error.show()


class BarChart(QWidget):
    def __init__(self, counts, parent=None):
        super().__init__(parent)
        self.counts = list(counts)
        self.setMinimumHeight(max(70, len(self.counts) * 36 + 8))
        self.setToolTip('\n'.join(f'{name}：{value}' for name, value in self.counts))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.palette().text().color())
        if not self.counts:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '暂无可统计的数据')
            return
        largest = max(1, max(value for _, value in self.counts))
        label_width = min(135, max(80, int(self.width() * .28)))
        usable = max(10, self.width() - label_width - 48)
        for row, (name, value) in enumerate(self.counts):
            y = row * 36 + 7
            painter.setPen(self.palette().text().color())
            text = painter.fontMetrics().elidedText(str(name), Qt.TextElideMode.ElideRight, label_width - 10)
            painter.drawText(0, y + 16, text)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.palette().alternateBase())
            painter.drawRoundedRect(label_width, y, usable, 21, 4, 4)
            painter.setBrush(QColor('#9281b8'))
            width = int(usable * value / largest)
            if width:
                painter.drawRoundedRect(label_width, y, width, 21, 4, 4)
            painter.setPen(self.palette().text().color())
            painter.drawText(label_width + usable + 10, y + 16, str(value))


def friendly_error(exc):
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, OSError):
        return '文件读写失败。请检查权限、磁盘空间或文件占用；输入已保留。'
    return '操作未完成。请检查数据文件或在设置中刷新后重试；没有提前应用本次修改。'


def apply_theme(app, dark):
    bg, side, panel, fg, muted, border, selected = (
        '#202226', '#1b1d21', '#292b30', '#e5e5eb', '#a4a6b0', '#3b3e46', '#40384f') if dark else (
        '#f8f9fb', '#f0f1f5', '#ffffff', '#292d37', '#737987', '#e3e5ec', '#ece7f5')
    palette = QPalette()
    for role, color in [(QPalette.ColorRole.Window, bg), (QPalette.ColorRole.Base, panel),
            (QPalette.ColorRole.AlternateBase, border), (QPalette.ColorRole.WindowText, fg),
            (QPalette.ColorRole.Text, fg), (QPalette.ColorRole.ButtonText, fg),
            (QPalette.ColorRole.Button, panel), (QPalette.ColorRole.Highlight, selected),
            (QPalette.ColorRole.HighlightedText, fg), (QPalette.ColorRole.ToolTipBase, panel),
            (QPalette.ColorRole.ToolTipText, fg), (QPalette.ColorRole.PlaceholderText, muted)]:
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(muted))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(muted))
    app.setPalette(palette)
    app.setStyleSheet(f'''
        QWidget {{ color: {fg}; font-family: "Microsoft YaHei UI"; font-size: 13px; }}
        QMainWindow, QWidget#appRoot {{ background: {bg}; }}
        QWidget#sidebar {{ background: {side}; border-right: 1px solid {border}; }}
        QFrame#card, QWidget#detailPanel {{ background: {panel}; border: 1px solid {border}; border-radius: 10px; }}
        QWidget#panelContent {{ background: {panel}; }}
        QLabel {{ background: transparent; border: none; }}
        QLabel#brand {{ font-size: 19px; font-weight: 600; }}
        QLabel#pageTitle {{ font-size: 25px; font-weight: 600; }}
        QLabel#panelTitle {{ font-size: 21px; font-weight: 600; }}
        QLabel#sectionTitle {{ font-size: 15px; font-weight: 600; }}
        QLabel#metric {{ font-size: 30px; font-weight: 600; }}
        QLabel#muted, QLabel#fieldLabel {{ color: {muted}; }}
        QLabel#eyebrow {{ color: {muted}; font-size: 11px; letter-spacing: 1px; }}
        QLabel#error {{ color: {'#f0a099' if dark else '#ac3a37'}; padding: 8px; }}
        QLabel#notice {{ background: {selected}; padding: 10px 14px; border-radius: 6px; }}
        QPushButton, QToolButton {{ background: {panel}; border: 1px solid {border}; border-radius: 6px; padding: 8px 12px; }}
        QPushButton:hover, QToolButton:hover {{ background: {selected}; border-color: #a094bc; }}
        QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus {{ border-color: #9281b8; }}
        QPushButton#primary {{ background: #79659f; color: #ffffff; border: 1px solid #79659f; font-weight: 600; }}
        QPushButton#primary:hover {{ background: #8974b1; }}
        QPushButton:disabled, QToolButton:disabled {{ color: {muted}; background: {bg}; border-color: {border}; }}
        QPushButton#primary:disabled {{ background: {border}; color: {muted}; border-color: {border}; }}
        QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {muted}; border-radius: 3px; background: {panel}; }}
        QCheckBox::indicator:checked {{ background: #9281b8; border-color: #9281b8; }}
        QLineEdit, QPlainTextEdit, QComboBox {{ background: {panel}; border: 1px solid {border}; border-radius: 6px; padding: 8px; min-height: 18px; selection-background-color: {selected}; }}
        QComboBox {{ padding-right: 22px; }}
        QComboBox::drop-down {{ width: 20px; border: none; }}
        QTableWidget {{ background: {panel}; border: none; border-radius: 6px; selection-background-color: {selected}; selection-color: {fg}; }}
        QTableWidget::item {{ padding: 8px; border-bottom: 1px solid {border}; }}
        QTableWidget::item:hover {{ background: {selected}; }}
        QTableWidget#friendsTable::item {{ padding: 5px 8px; }}
        QTableWidget#friendsTable::indicator {{ width: 14px; height: 14px; border: 1px solid {muted}; border-radius: 7px; background: {panel}; }}
        QTableWidget#friendsTable::indicator:checked {{ background: #9281b8; border: 3px solid {panel}; }}
        QCheckBox::indicator:indeterminate {{ background: #b2a2cf; border-color: #9281b8; }}
        QWidget#managementBar {{ background: {selected}; border-radius: 8px; }}
        QHeaderView::section {{ background: {panel}; color: {muted}; border: none; border-bottom: 1px solid {border}; padding: 12px 8px; font-weight: 400; }}
        QListWidget#navigation {{ border: none; background: transparent; outline: none; }}
        QListWidget#navigation::item {{ padding: 11px 12px; margin: 2px 0; border-radius: 6px; }}
        QListWidget#navigation::item:selected {{ background: {selected}; color: {fg}; }}
        QListWidget#navigation::item:hover {{ background: {selected}; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ width: 9px; background: transparent; margin: 2px; }}
        QScrollBar::handle:vertical {{ background: {border}; border-radius: 3px; min-height: 24px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QTabWidget::pane {{ border: none; }}
        QTabBar::tab {{ padding: 10px 10px; border-bottom: 2px solid transparent; color: {muted}; }}
        QTabBar::tab:selected {{ color: {fg}; border-bottom: 2px solid #9281b8; }}
        QMenu {{ background: {panel}; border: 1px solid {border}; padding: 5px; }}
        QMenu::item {{ padding: 8px 22px; border-radius: 4px; }}
        QMenu::item:selected {{ background: {selected}; }}
        QStatusBar {{ color: {muted}; border-top: 1px solid {border}; }}
        QProgressBar {{ border: none; background: {border}; max-height: 3px; }}
        QProgressBar::chunk {{ background: #9281b8; }}
        QSplitter::handle {{ background: transparent; width: 8px; height: 8px; }}
        QToolTip {{ background: {panel}; color: {fg}; border: 1px solid {border}; padding: 5px; }}
    ''')
