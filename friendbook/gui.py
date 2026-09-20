"""Modern desktop shell. Widgets use only the Store business interface."""
from PySide6.QtCore import Qt, QSettings, QTimer, QSize
from PySide6.QtGui import QAction, QKeySequence, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout,
    QHBoxLayout, QListWidget, QLineEdit, QComboBox, QCheckBox, QStackedWidget,
    QTableWidgetItem, QMessageBox, QMenu, QToolButton, QProgressBar, QHeaderView)
from .core import new_record
from .labels import record_labels
from .ui_widgets import (label, button, scroll_content, clear_layout, Avatar, Editor, avatar_icon,
                         configure_table, friendly_error, apply_theme)
from .ui_tasks import StoreTask
from .ui_pages import Pages
from .ui_actions import DataActions
from .ui_management import ListManagement
from .ui_friend_list import FriendsTable
from .ui_motion import DrawerWorkspace, ClickFeedback, Ripple
from .ui_charts import DistributionChart
from .contact_fields import PROFILE_FIELDS, grouped_contacts, contact_caption


class Window(QMainWindow, Pages, DataActions, ListManagement):
    PAGE_NAMES = ('概览', '好友', '分组', '统计', '导入与备份', '回收站', '设置', '链表教学')
    DESCRIPTIONS = dict(zip(PAGE_NAMES, (
        '看见每一份关系，也留意那些还未知的信息。', '整理资料，记录共同的兴趣与故事。',
        '用自己的方式整理关系。', '基于有效档案的真实统计；缺失信息单独呈现。',
        '导入新增记录，恢复替换整个数据集。', '误删可以还原，永久删除前请仔细确认。',
        '你的本地空间，按习惯使用。', '课程工具 · 查看运行时双向链表的真实连接。')))

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.settings = QSettings(str(store.path.parent / 'settings.ini'), QSettings.Format.IniFormat)
        self.dark = self.settings.value('dark', False, bool)
        self.setProperty('reduceMotion', self.settings.value('reduce_motion', False, bool))
        self.click_feedback = ClickFeedback(self)
        self.managing = False
        self._checked_ids = set()
        self.page_name = '好友'
        self._selected_id = None
        self.editor = None
        self.editor_context = {}
        self._after_save = None
        self._busy = False
        self._tasks = set()
        self._filters = ('', None, '', False, 0)
        self._visible_records = []
        self.compact_detail = False
        self.setWindowTitle('好友档案 · Friendbook')
        self.setMinimumSize(820, 580)
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1280, int(available.width() * .95)), min(820, int(available.height() * .92)))
        self.workspace = QWidget()
        self.workspace.setObjectName('appRoot')
        self.setCentralWidget(self.workspace)
        root = QHBoxLayout(self.workspace)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = QWidget()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setFixedWidth(184)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(18, 26, 18, 18)
        side.setSpacing(8)
        side.addWidget(label('好友档案', 'brand'))
        side.addWidget(label('FRIENDBOOK', 'eyebrow'))
        side.addSpacing(28)
        side.addWidget(label('我的空间', 'eyebrow'))
        self.nav = QListWidget()
        self.nav.setObjectName('navigation')
        self.nav.addItems(self.PAGE_NAMES)
        self.nav.setCurrentRow(1)
        self.nav.currentRowChanged.connect(self._navigation_changed)
        side.addWidget(self.nav, 1)
        self.sidebar_count = label('', 'muted', True)
        side.addWidget(self.sidebar_count)
        side.addWidget(label('仅保存在这台电脑', 'eyebrow'))
        root.addWidget(self.sidebar)
        center = QVBoxLayout()
        center.setContentsMargins(24, 24, 24, 16)
        center.setSpacing(12)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.heading = label('好友', 'pageTitle')
        self.subtitle = label(self.DESCRIPTIONS['好友'], 'muted', True)
        titles.addWidget(self.heading)
        titles.addWidget(self.subtitle)
        heading.addLayout(titles, 1)
        self.add_button = button('＋ 添加好友', lambda: self.add(), True)
        heading.addWidget(self.add_button)
        center.addLayout(heading)
        self.notice = label('', 'notice', True)
        self.notice.hide()
        center.addWidget(self.notice)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        center.addWidget(self.progress)
        self.pages = QStackedWidget()
        center.addWidget(self.pages, 1)
        root.addLayout(center, 1)
        friends = self.build_friends()
        self.page_widgets = {'好友': friends, '回收站': friends}
        self.pages.addWidget(friends)
        for name, builder in [('概览', self.build_home), ('分组', self.build_groups), ('统计', self.build_statistics),
                ('导入与备份', self.build_data_page), ('设置', self.build_settings), ('链表教学', self.build_teaching)]:
            self.page_widgets[name] = builder()
            self.pages.addWidget(self.page_widgets[name])
        self.pages.setCurrentWidget(friends)
        self.statusBar().showMessage('就绪 · 本地保存')
        for shortcut, callback in [('Ctrl+N', self.add), ('Ctrl+F', self.focus_search), ('Ctrl+S', self.save_editor)]:
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(lambda checked=False, fn=callback: fn())
            self.addAction(action)
        self.apply_theme()
        self.refresh_all()
        self._resize_workspace()

    def build_friends(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        search_row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText('搜索好友、兴趣、联系方式或备注…')
        self.query.setClearButtonEnabled(True)
        search_row.addWidget(self.query, 1)
        self.favorites = QCheckBox('仅收藏')
        search_row.addWidget(self.favorites)
        self.filters_button = button('筛选与排序', self.toggle_filters)
        search_row.addWidget(self.filters_button)
        self.management_button = button('☰ 管理列表', self.toggle_management)
        search_row.addWidget(self.management_button)
        layout.addLayout(search_row)
        self.filters_widget = QWidget()
        filter_row = QHBoxLayout(self.filters_widget)
        filter_row.setContentsMargins(0, 0, 0, 0)
        self.group = QComboBox()
        self.group.setMinimumWidth(105)
        self.tag = QLineEdit()
        self.tag.setPlaceholderText('精确备注')
        self.tag.setClearButtonEnabled(True)
        self.sort = QComboBox()
        self.sort.addItems(['原始顺序', '姓名升序 · 临时', '出生信息升序 · 临时'])
        filter_row.addWidget(self.group, 1)
        filter_row.addWidget(self.tag, 1)
        filter_row.addWidget(self.sort, 1)
        filter_row.addWidget(button('重置', lambda: self.request_leave(lambda: self.set_filters(('', None, '', False, 0)))))
        layout.addWidget(self.filters_widget)
        self.filters_widget.hide()
        self.hint = label('', 'muted', True)
        layout.addWidget(self.hint)
        layout.addWidget(self.build_management_bar())
        self.splitter = DrawerWorkspace()
        layout.addWidget(self.splitter, 1)
        self.list_area = QFrame()
        self.list_area.setObjectName('card')
        list_layout = QVBoxLayout(self.list_area)
        list_layout.setContentsMargins(8, 2, 8, 8)
        self.table = FriendsTable()
        configure_table(self.table)
        self.table.setHorizontalHeaderLabels(['好友', '标签', '兴趣', '出生信息'])
        self.table.setIconSize(QSize(32, 32))
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 225)
        self.table.toggle_requested.connect(self.toggle_friend_check)
        self.table.select_all_requested.connect(self.toggle_all_friends)
        self.table.reorder_requested.connect(self.reorder_friends)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemClicked.connect(self._item_clicked)
        self.table.doubleClicked.connect(self.edit)
        list_layout.addWidget(self.table, 1)
        self.empty_title = label('还没有好友', 'sectionTitle', True)
        self.empty_message = label('添加第一位好友，或在“导入与备份”中导入已有档案。', 'muted', True)
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_box = QWidget()
        empty_layout = QVBoxLayout(self.empty_box)
        empty_layout.setSpacing(12)
        empty_layout.addStretch()
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_message)
        empty_layout.addStretch()
        list_layout.addWidget(self.empty_box, 1)
        self.splitter.addWidget(self.list_area)
        self.detail_panel = QWidget()
        self.detail_panel.setObjectName('detailPanel')
        self.detail_panel.setMinimumWidth(340)
        panel_layout = QVBoxLayout(self.detail_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        self.back_button = button('← 返回好友列表', self.back_to_list)
        panel_layout.addWidget(self.back_button)
        self.panel_stack = QStackedWidget()
        panel_layout.addWidget(self.panel_stack, 1)
        self.detail, self.detail_layout = scroll_content()
        self.detail.widget().setObjectName('panelContent')
        self.detail_layout.setContentsMargins(20, 18, 20, 18)
        self.panel_stack.addWidget(self.detail)
        self.splitter.addWidget(self.detail_panel)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self._filters_changed)
        self.query.textChanged.connect(lambda: self.search_timer.start())
        self.tag.textChanged.connect(lambda: self.search_timer.start())
        self.group.currentIndexChanged.connect(self._filters_changed)
        self.sort.currentIndexChanged.connect(self._filters_changed)
        self.favorites.toggled.connect(self._filters_changed)
        self.more_menu = QMenu(self)
        self.before_button = self.more_menu.addAction('在此好友前添加', lambda: self.add(before=True))
        self.after_button = self.more_menu.addAction('在此好友后添加', lambda: self.add(before=False))
        self.more_menu.addSeparator()
        self.up_button = self.more_menu.addAction('按原始顺序上移', lambda: self.move(-1))
        self.down_button = self.more_menu.addAction('按原始顺序下移', lambda: self.move(1))
        self.more_menu.addSeparator()
        self.merge_button = self.more_menu.addAction('检测重复 / 合并', self.merge)
        return page

    def selected(self):
        return self._selected_id

    def table_uid(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _navigation_changed(self, row):
        if row >= 0:
            target = self.PAGE_NAMES[row]
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(self.PAGE_NAMES.index(self.page_name))
            self.nav.blockSignals(False)
            self.navigate(target)

    def navigate(self, name):
        if name in self.PAGE_NAMES and name != self.page_name and not self._busy:
            self.request_leave(lambda: self._set_page(name))

    def _set_page(self, name):
        old = self.page_name
        if self.managing and name != '好友':
            self.request_leave_management(lambda: self._set_page(name))
            return
        self.page_name = name
        self.nav.blockSignals(True)
        self.nav.setCurrentRow(self.PAGE_NAMES.index(name))
        self.nav.blockSignals(False)
        self.heading.setText(name)
        self.subtitle.setText(self.DESCRIPTIONS[name])
        self.pages.setCurrentWidget(self.page_widgets[name])
        self.add_button.setVisible(name in ('好友', '概览'))
        self.management_button.setVisible(name == '好友')
        if name in ('好友', '回收站'):
            if old != name:
                self._selected_id = None
                self.compact_detail = False
                self.set_filters(('', None, '', False, 0))
            self.refresh_friends()
        self.refresh_current_page()
        self._resize_workspace()

    def request_leave(self, action):
        if self._busy:
            return
        self.search_timer.stop()
        self._write_filters(self._filters)
        if self.has_draft_changes():
            decision = self.unsaved_choice()
            if decision == QMessageBox.StandardButton.Cancel:
                return
            if decision == QMessageBox.StandardButton.Save:
                self._after_save = action
                self.save_editor()
                return
        self.discard_editor()
        action()

    def has_draft_changes(self):
        return bool(self.editor and (self.editor.dirty() or self.editor_context.get('source') or
                    (self.editor_context.get('expected') is None and self.editor.original['group'])))

    def unsaved_choice(self):
        box = QMessageBox(self)
        box.setWindowTitle('未保存的修改')
        box.setText('要先保存当前草稿吗？')
        box.setInformativeText('保存成功后才会继续操作。取消将留在当前好友。')
        box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        for standard, text in [(QMessageBox.StandardButton.Save, '保存并继续'), (QMessageBox.StandardButton.Discard, '放弃修改'), (QMessageBox.StandardButton.Cancel, '取消切换')]:
            box.button(standard).setText(text)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec()

    def confirm(self, title, text):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.button(QMessageBox.StandardButton.Yes).setText('确认')
        box.button(QMessageBox.StandardButton.No).setText('取消')
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def notify(self, text, error=False):
        self.notice.setText(text)
        self.notice.setObjectName('error' if error else 'notice')
        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)
        self.notice.show()
        self.statusBar().showMessage('操作未完成' if error else '就绪 · 本地保存')

    def refresh_all(self):
        total, trash = self.store.counts()
        self.sidebar_count.setText(f'{total} 位好友\n回收站 {trash} 份')
        self.refresh_groups()
        self.refresh_friends()
        self.refresh_current_page()

    def refresh_current_page(self):
        handlers = {'概览': self.refresh_home, '分组': self.refresh_group_page,
                    '统计': self.refresh_statistics, '链表教学': self.refresh_teaching}
        if self.page_name in handlers:
            handlers[self.page_name]()

    def refresh_groups(self):
        current = self._filters[1]
        self.group.blockSignals(True)
        self.group.clear()
        self.group.addItem('全部标签', None)
        self.group.addItem('（未设置标签）', '')
        for name in self.friend_source().label_names():
            self.group.addItem(name, name)
        index = self.group.findData(current)
        if current is not None and index < 0:
            self.group.addItem(current + '（暂无好友）', current)
            index = self.group.count() - 1
        self.group.setCurrentIndex(max(0, index))
        self.group.blockSignals(False)

    def filter_values(self):
        return self.query.text(), self.group.currentData(), self.tag.text(), self.favorites.isChecked(), self.sort.currentIndex()

    def _write_filters(self, values):
        controls = (self.query, self.group, self.tag, self.favorites, self.sort)
        for control in controls:
            control.blockSignals(True)
        self.query.setText(values[0])
        if self.group.findData(values[1]) < 0 and values[1] is not None:
            self.group.addItem(values[1] or '（未设置标签）', values[1])
        self.group.setCurrentIndex(max(0, self.group.findData(values[1])))
        self.tag.setText(values[2])
        self.favorites.setChecked(values[3])
        self.sort.setCurrentIndex(values[4])
        for control in controls:
            control.blockSignals(False)

    def _filters_changed(self, *_):
        values = self.filter_values()
        if values != self._filters:
            self._write_filters(self._filters)
            self.request_leave(lambda: self.set_filters(values))

    def set_filters(self, values):
        if values != self._filters:
            self._checked_ids.clear()
        self._filters = values
        self._write_filters(values)
        if values[1] is not None or values[2] or values[4]:
            self.filters_widget.show()
        self.refresh_friends()

    def toggle_filters(self):
        self.filters_widget.setVisible(not self.filters_widget.isVisible())

    def refresh_friends(self):
        trash = self.page_name == '回收站'
        query, group, tag, favorites, sort = self._filters
        source = self.friend_source()
        records = source.records(query, group, tag.strip(), favorites, trash)
        if sort:
            key = 'name' if sort == 1 else 'birth'
            records.sort(key=lambda r: (not bool(r[key]), r[key].casefold(), r['id']))
        self._visible_records = records
        self.table.configure_management(self.managing, self._checked_ids, self.can_reorder())
        self.table.setHorizontalHeaderLabels(['好友', '标签', '兴趣', '出生信息'] + (['移动'] if self.managing else []))
        if self.managing:
            self.table.horizontalHeader().setMinimumSectionSize(38)
            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(4, 40)
        self.table.blockSignals(True)
        self.table.setRowCount(len(records))
        self.table.setCurrentCell(-1, -1)
        visible = False
        for row, record in enumerate(records):
            values = [('★  ' if record['favorite'] else '') + (record['name'] or '未命名好友'),
                      ' · '.join(record_labels(record)) or '未设置标签', record['interests'] or '—', record['birth'] or '未知']
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record['id'])
                item.setToolTip(value)
                if col == 0:
                    item.setIcon(avatar_icon(record, self.table.iconSize().width()))
                    if self.managing:
                        item.setCheckState(Qt.CheckState.Checked if record['id'] in self._checked_ids else Qt.CheckState.Unchecked)
                    font = item.font()
                    font.setWeight(QFont.Weight.DemiBold)
                    item.setFont(font)
                self.table.setItem(row, col, item)
            if self.managing:
                handle = QTableWidgetItem('')
                handle.setData(Qt.ItemDataRole.UserRole, record['id'])
                handle.setToolTip('长按或拖动：移动此好友；若已勾选，整体移动所有已选好友' if self.can_reorder() else
                                  '拖动仅用于全部好友的原始顺序，请先重置筛选与排序')
                handle.setData(Qt.ItemDataRole.AccessibleTextRole, handle.toolTip())
                self.table.setItem(row, 4, handle)
            if record['id'] == self._selected_id:
                self.table.selectRow(row)
                visible = True
        self.table.blockSignals(False)
        if not visible and not self.editor:
            self._selected_id = None
            self.compact_detail = False
        self.favorites.setEnabled(not trash)
        self.query.setPlaceholderText('搜索回收站中的姓名或备注…' if trash else '搜索好友、兴趣、联系方式或备注…')
        self.group.setEnabled(not trash)
        self.tag.setEnabled(not trash)
        total = source.counts()[int(trash)]
        self.hint.setText(f'显示 {len(records)} / {total} 位  ·  ' + ('还原后置于原始顺序末尾' if trash else ('临时排序仅改变显示顺序' if sort else '原始顺序')))
        if self.managing:
            self.hint.setText(self.hint.text() + (' · 拖动右侧手柄调整顺序；Esc 取消拖动' if self.can_reorder() else
                                                 ' · 当前仅可批量操作；重置筛选和排序后可拖动'))
        self.empty_title.setVisible(not records)
        self.empty_message.setVisible(not records)
        self.empty_box.setVisible(not records)
        self.table.setVisible(bool(records))
        self.empty_title.setText('没有匹配的好友' if total else ('回收站为空' if trash else '从第一位好友开始'))
        self.empty_message.setText('尝试清除关键词或重置筛选条件。' if total else (
            '移入回收站的档案会出现在这里，之后可以还原。' if trash else '点击右上角添加好友，或前往“导入与备份”。'))
        if not self.editor:
            self.render_detail()
        self.update_actions()
        self.update_management_selection()
        self._resize_workspace()

    def _selection_changed(self):
        if self.managing:
            return
        uid = self.table_uid()
        if uid != self._selected_id:
            self._select_table(self._selected_id)
            self.request_leave(lambda: self.select_uid(uid))

    def _item_clicked(self, item):
        if self.managing:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        if uid == self._selected_id and not self.compact_detail:
            self.request_leave(lambda: self.select_uid(uid))

    def _select_table(self, uid):
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == uid:
                self.table.selectRow(row)
                break
        self.table.blockSignals(False)

    def select_uid(self, uid):
        if self.managing:
            return
        self._selected_id = uid if uid in {r['id'] for r in self._visible_records} else None
        self._select_table(self._selected_id)
        self.compact_detail = bool(self._selected_id)
        self.render_detail()
        self.update_actions()
        self._resize_workspace()

    def render_detail(self):
        if self.editor:
            return
        clear_layout(self.detail_layout)
        self.panel_stack.setCurrentWidget(self.detail)
        if not self._selected_id:
            self.detail_layout.addStretch()
            self.detail_layout.addWidget(label('选一位好友，了解更多', 'panelTitle', True))
            self.detail_layout.addWidget(label('资料、联系方式、自定义属性与备注会显示在这里。', 'muted', True))
            self.detail_layout.addStretch()
            return
        try:
            record = self.store.record(self._selected_id, self.page_name == '回收站')
        except KeyError:
            self._selected_id = None
            return self.render_detail()
        header = QHBoxLayout()
        header.addWidget(Avatar(record, 76))
        header.addStretch()
        if self.page_name != '回收站':
            self.favorite_button = button('★' if record['favorite'] else '☆', lambda: self.toggle_favorite(record['id']))
            self.favorite_button.setCheckable(True)
            self.favorite_button.setChecked(record['favorite'])
            self.favorite_button.setFixedSize(44, 44)
            self.favorite_button.setStyleSheet('font-size: 28px; padding: 0; color: #97804f;')
            self.favorite_button.setToolTip('取消收藏' if record['favorite'] else '收藏好友')
            self.favorite_button.setAccessibleName(self.favorite_button.toolTip())
            header.addWidget(self.favorite_button, 0, Qt.AlignmentFlag.AlignTop)
        self.detail_layout.addLayout(header)
        self.detail_layout.addWidget(label(record['name'] or '未命名好友', 'panelTitle', True))
        self.detail_layout.addWidget(label(' · '.join(record_labels(record)) or '未设置标签', 'muted', True))
        actions = QHBoxLayout()
        trash = self.page_name == '回收站'
        self.edit_button = button('还原好友' if trash else '编辑资料', self.edit, True)
        self.delete_button = button('永久删除' if trash else '移入回收站', self.delete)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.delete_button)
        if not trash:
            more = QToolButton()
            more.setText('更多')
            more.setToolTip('前后添加、调整原始顺序、检测重复与合并')
            more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            more.setMenu(self.more_menu)
            actions.addWidget(more)
        self.detail_layout.addLayout(actions)
        if not trash and not self.can_reorder():
            self.detail_layout.addWidget(label('筛选或临时排序中：前后添加以当前好友在原始顺序中的位置为准；上下移动暂不可用。', 'muted', True))
        for title, value in [('出生信息', record['birth'] or '未知'), ('兴趣', record['interests'] or '未填写'), ('备注', ' · '.join(record['tags']) or '未填写')]:
            self.detail_layout.addWidget(label(title, 'fieldLabel'))
            item = label(value, '', True)
            item.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.detail_layout.addWidget(item)
        if any(record['custom'].get(k) for k in PROFILE_FIELDS):
            self.detail_layout.addWidget(label('更多资料', 'sectionTitle'))
            for key in PROFILE_FIELDS:
                if record['custom'].get(key):
                    self.detail_layout.addWidget(label(key, 'fieldLabel'))
                    self.detail_layout.addWidget(label(record['custom'][key], '', True))
        self.detail_layout.addWidget(label('联系方式', 'sectionTitle'))
        if not record['contacts']:
            self.detail_layout.addWidget(label('未填写', 'muted'))
        for kind, entries in grouped_contacts(record['contacts']).items():
            if not entries:
                continue
            self.detail_layout.addWidget(label(kind, 'fieldLabel'))
            for index, (name, value) in enumerate(entries):
                caption = contact_caption(kind, index, len(entries), name)
                text = (caption + '：' if caption != kind or len(entries) > 1 else '') + (value or '未填写')
                item = label(text, '', True)
                item.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self.detail_layout.addWidget(item)
        custom = {name: value for name, value in record['custom'].items() if name not in PROFILE_FIELDS}
        self.detail_layout.addSpacing(6)
        self.detail_layout.addWidget(label('自定义属性', 'sectionTitle'))
        if not custom:
            self.detail_layout.addWidget(label('未填写', 'muted'))
        for name, value in custom.items():
            self.detail_layout.addWidget(label(name, 'fieldLabel', True))
            item = label(value or '未填写', '', True)
            item.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.detail_layout.addWidget(item)
        self.detail_layout.addSpacing(6)
        self.detail_layout.addWidget(label('详细备注', 'sectionTitle'))
        notes = label(record['notes'] or '还没有备注。', '', True)
        notes.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_layout.addWidget(notes)
        self.detail_layout.addStretch()

    def toggle_favorite(self, uid):
        if self._busy or self.managing or self.editor or self.page_name == '回收站':
            return
        record = self.store.record(uid)
        record['favorite'] = not record['favorite']
        self.start_task('save', (record,), {'expected': record['version']},
                        success=lambda _: self.notify('已加入收藏。' if record['favorite'] else '已取消收藏。'))

    def can_reorder(self):
        return self.page_name == '好友' and self._filters == ('', None, '', False, 0)

    def update_actions(self):
        valid = bool(self._selected_id) and self.page_name == '好友'
        for action in (self.before_button, self.after_button, self.merge_button):
            action.setEnabled(valid)
        for action in (self.up_button, self.down_button):
            action.setEnabled(valid and self.can_reorder())
            action.setToolTip('仅在全部好友、无筛选且按原始顺序显示时可用')

    def add(self, before=None, group=''):
        if self._busy:
            return
        if self.managing:
            self.request_leave_management(lambda: self.add(before, group))
            return
        anchor = self._selected_id if before is not None else None
        if before is not None and (not anchor or self.page_name != '好友'):
            return
        def begin():
            if self.managing:
                self.set_management(False)
            if self.page_name != '好友':
                self._set_page('好友')
            record = new_record()
            record['group'] = group
            self.open_editor(record, '添加好友', anchor=anchor, before=bool(before))
        self.request_leave(begin)

    def edit(self, *_):
        if self._busy or self.managing or not self._selected_id or self.editor:
            return
        uid = self._selected_id
        if self.page_name == '回收站':
            self.start_task('restore_item', (uid,), success=lambda _: self.notify('已还原好友，放在原始顺序末尾。'), text='正在还原好友…')
            return
        record = self.store.record(uid)
        self.open_editor(record, '编辑好友', expected=record['version'])

    def open_editor(self, record, title, **context):
        self.discard_editor(render=False)
        self.editor_context = context
        self.editor = Editor(record, title, self.detail_panel, available_labels=self.store.label_names())
        self.editor.save_requested.connect(self.save_editor)
        self.editor.cancel_requested.connect(lambda: self.request_leave(self.render_detail))
        self.panel_stack.addWidget(self.editor)
        self.panel_stack.setCurrentWidget(self.editor)
        self.compact_detail = True
        self._resize_workspace()

    def discard_editor(self, render=True):
        if self.editor:
            editor, self.editor = self.editor, None
            self.panel_stack.removeWidget(editor)
            editor.deleteLater()
            self.editor_context = {}
        if render:
            self.render_detail()

    def save_editor(self):
        if not self.editor or self._busy:
            return
        try:
            record = self.editor.validated()
        except Exception as exc:
            self.editor.show_error(friendly_error(exc))
            self._after_save = None
            return
        context = self.editor_context
        if not context.get('source'):
            duplicates = self.store.duplicate_records(record)
            if duplicates and not self.confirm('疑似重复档案', f'发现 {len(duplicates)} 份同名或相同联系方式档案。仍单独保存？不会自动覆盖或合并。'):
                self._after_save = None
                return
        if context.get('source'):
            method, args, kwargs = 'merge', (record['id'], context['source'], record, context['expected']), {}
        else:
            method, args, kwargs = 'save', (record,), dict(anchor=context.get('anchor'), before=context.get('before', False), expected=context.get('expected'))
        def finished(_):
            next_action, self._after_save = self._after_save, None
            self.discard_editor(render=False)
            self.refresh_friends()
            self.select_uid(record['id'])
            self.notify('好友已保存。' if self._selected_id else '好友已保存；当前筛选条件下不显示该好友。')
            if next_action:
                next_action()
        self.start_task(method, args, kwargs, finished, '正在保存好友…')

    def delete(self):
        if not self._selected_id or self._busy:
            return
        def run():
            uid = self._selected_id
            if not uid:
                return
            trash = self.page_name == '回收站'
            if self.confirm('永久删除' if trash else '移入回收站', '永久删除好友及照片？此操作不可撤销。' if trash else '将当前好友移入回收站？之后可以还原。'):
                self.start_task('purge' if trash else 'delete', (uid,), success=lambda _: self.notify('已永久删除该档案。' if trash else '已移入回收站，可以在回收站还原。'), text='正在处理档案…')
        self.request_leave(run)

    def move(self, direction):
        if self._selected_id and self.can_reorder() and not self._busy:
            uid = self._selected_id
            self.request_leave(lambda: self.start_task('move_relative', (uid, direction), success=lambda _: self.notify('原始顺序已保存。'), text='正在调整顺序…'))

    def open_friend(self, uid):
        if self.managing:
            self.request_leave_management(lambda: self.open_friend(uid))
            return
        def show():
            if self.managing:
                self.set_management(False)
            self._set_page('好友')
            self.set_filters(('', None, '', False, 0))
            self.select_uid(uid)
        self.request_leave(show)

    def back_to_list(self):
        def back():
            self.compact_detail = False
            self._resize_workspace()
        self.request_leave(back)

    def focus_search(self):
        def focus():
            if self.page_name != '好友':
                self._set_page('好友')
            self.query.setFocus()
        self.request_leave(focus)

    def reload(self):
        if self.managing:
            self.request_leave_management(self.reload)
            return
        self.request_leave(lambda: self.start_task('reload', text='正在刷新磁盘数据…', success=lambda _: self.notify('已重新读取磁盘数据。')))

    def start_task(self, method, args=(), kwargs=None, success=None, text='正在处理…'):
        if self._busy:
            return
        self._busy = True
        self.progress.show()
        self.workspace.setEnabled(False)
        self.statusBar().showMessage(text)
        task = StoreTask(self.store.path, self.store.revision, method, args, kwargs, self)
        self._tasks.add(task)
        def completed(snapshot):
            result, book, trash, revision, catalog = snapshot
            self.store.adopt(book, trash, revision, catalog)
            self._busy = False
            self.workspace.setEnabled(True)
            self.progress.hide()
            self.refresh_all()
            self.statusBar().showMessage('就绪 · 本地保存')
            if success:
                success(result)
        def failed(exc):
            self._busy = False
            self._after_save = None
            self.workspace.setEnabled(True)
            self.progress.hide()
            self.notify(friendly_error(exc), True)
            if self.editor:
                self.editor.show_error(friendly_error(exc))
            else:
                self.render_detail()
        def finished():
            self._tasks.discard(task)
            task.deleteLater()
        task.completed.connect(completed)
        task.failed.connect(failed)
        task.finished.connect(finished)
        task.start()

    def set_theme(self, dark):
        self.dark = dark
        self.settings.setValue('dark', dark)
        self.theme_choice.blockSignals(True)
        self.theme_choice.setCurrentIndex(int(dark))
        self.theme_choice.blockSignals(False)
        self.apply_theme()

    def toggle_theme(self):
        self.set_theme(not self.dark)

    def apply_theme(self):
        apply_theme(QApplication.instance(), self.dark)

    def teaching(self):
        self.navigate('链表教学')

    def statistics(self):
        self.navigate('统计')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'splitter'):
            self._resize_workspace()

    def _resize_workspace(self):
        compact = self.width() < 1120
        self.sidebar.setFixedWidth(154 if self.width() < 1000 else 184)
        self.back_button.setText('← 返回好友列表' if compact else '关闭详情 ×')
        opened = not self.managing and bool(self.editor or (self._selected_id and self.compact_detail))
        self.splitter.set_open(opened, compact)

    def set_reduce_motion(self, reduced):
        self.setProperty('reduceMotion', reduced)
        self.settings.setValue('reduce_motion', reduced)
        self.splitter.finish_motion()
        self.table.cancel_drag()
        self.management_bar.finish_motion()
        if reduced:
            for chart in self.stats_tabs.findChildren(DistributionChart):
                chart.animation.stop()
                chart._progress_changed(1.)
        for effect in self.findChildren(Ripple):
            effect.hide()
            effect.deleteLater()

    def closeEvent(self, event):
        if self._busy:
            self.statusBar().showMessage('正在保存或处理文件，请等待完成后关闭。')
            event.ignore()
            return
        if self.managing:
            event.ignore()
            self.request_leave_management(self.close)
            return
        if self.has_draft_changes():
            event.ignore()
            self.request_leave(self.close)
            return
        for task in tuple(self._tasks):
            task.wait(1000)
        self.settings.sync()
        QApplication.instance().removeEventFilter(self.click_feedback)
        self.table.cancel_drag()
        self.splitter.finish_motion()
        event.accept()
