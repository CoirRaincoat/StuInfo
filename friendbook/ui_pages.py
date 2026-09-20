"""Overview, groups, statistics and utilities; all metrics come from Store."""
from datetime import date
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTableWidget,
    QTableWidgetItem, QComboBox, QInputDialog, QHeaderView, QCheckBox, QTabWidget, QPushButton, QDialog, QSizePolicy)
from .ui_widgets import label, button, card, scroll_content, clear_layout, BarChart, configure_table, avatar_icon
from .ui_charts import DistributionChart
from .labels import record_labels


class MetricButton(QPushButton):
    """A metric card is a real keyboard-accessible button across its whole surface."""
    def __init__(self, title, value, note, callback):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f'{title}：{value}，点击查看好友')
        content = QVBoxLayout(self)
        content.setContentsMargins(20, 18, 20, 18)
        content.setSpacing(12)
        for text, role, wrap in ((title, 'muted', False), (str(value), 'metric', False), (note, 'muted', True)):
            text_label = label(text, role, wrap)
            text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            content.addWidget(text_label)
        self.clicked.connect(callback)


class Pages:
    def build_home(self):
        page, self.home_layout = scroll_content()
        return page

    def refresh_home(self):
        clear_layout(self.home_layout)
        data = self.store.overview()
        metrics = QGridLayout()
        for i, (title, value, note, collection) in enumerate([
                ('好友', data['total'], '全部有效档案', None),
                ('本月生日', len(data['birthdays']), f"查看本月好友 · {data['month_unknown']} 位月份未知", 'birthdays'),
                ('收藏', data['favorites'], '点击查看收藏的好友', 'favorites'),
                ('标签', sum(bool(k) for k in data['groups']), '好友可以拥有多个标签', None)]):
            if collection:
                frame = MetricButton(title, value, note, lambda checked=False, key=collection: self.show_collection(key))
                setattr(self, f'home_{collection}_card', frame)
            else:
                frame, content = card()
                content.addWidget(label(title, 'muted'))
                content.addWidget(label(str(value), 'metric'))
                content.addWidget(label(note, 'muted', True))
            metrics.addWidget(frame, 0, i)
            metrics.setColumnStretch(i, 1)
        self.home_layout.addLayout(metrics)
        frame, content = card(f'{date.today().month} 月生日', '已知到月份即可纳入；没有出生日期，不推断具体哪天生日。')
        for record in data['birthdays'][:6]:
            row = QHBoxLayout()
            row.addWidget(label(record['name'] or '未命名好友', '', True), 1)
            row.addWidget(label(record['birth'], 'muted'))
            row.addWidget(button('查看好友', lambda checked=False, uid=record['id']: self.open_friend(uid)))
            content.addLayout(row)
        if not data['birthdays']:
            content.addWidget(label('本月暂无已知生日的好友。', 'muted'))
        if len(data['birthdays']) > 6:
            content.addWidget(button(f"查看全部 {len(data['birthdays'])} 位", lambda: self.show_collection('birthdays')))
        self.home_layout.addWidget(frame)
        frame, content = card('标签一览', '按全部有效好友统计；一位好友可以计入多个标签')
        content.addWidget(BarChart([(name or '（未标记）', count) for name, count in data['groups'].most_common(6)]))
        content.addWidget(button('管理标签', lambda: self.navigate('分组')))
        self.home_layout.addWidget(frame)
        self.home_layout.addStretch()

    def show_collection(self, collection):
        previous = getattr(self, 'collection_dialog', None)
        if previous:
            previous.close()
        records = ([self.store.record(record['id']) for record in self.store.overview()['birthdays']] if collection == 'birthdays'
                   else self.store.records(favorites=True))
        title = f'{date.today().month} 月生日好友' if collection == 'birthdays' else '收藏的好友'
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setWindowTitle(title)
        dialog.resize(680, 460)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(title, 'panelTitle'))
        layout.addWidget(label(f'共 {len(records)} 位 · 点击好友查看详情', 'muted'))
        table = QTableWidget(len(records), 3)
        table.setObjectName('overviewCollection')
        configure_table(table)
        table.setHorizontalHeaderLabels(['好友', '出生信息', '标签'])
        for row, record in enumerate(records):
            name = QTableWidgetItem(record['name'] or '未命名好友')
            name.setIcon(avatar_icon(record))
            name.setData(Qt.ItemDataRole.UserRole, record['id'])
            table.setItem(row, 0, name)
            table.setItem(row, 1, QTableWidgetItem(record['birth'] or '未知'))
            table.setItem(row, 2, QTableWidgetItem(' · '.join(record_labels(record)) or '未标记'))
        table.setCurrentCell(-1, -1)
        layout.addWidget(table, 1)
        if not records:
            layout.addWidget(label('本月暂无已知生日的好友。' if collection == 'birthdays' else '还没有收藏的好友。', 'muted'))
        if collection == 'birthdays':
            layout.addWidget(label('按已知出生月份列出全部好友；仅填写年份的档案不计入。', 'muted', True))
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(button('关闭', dialog.close))
        layout.addLayout(close_row)
        def open_row(row, _column=0):
            item = table.item(row, 0)
            if item:
                uid = item.data(Qt.ItemDataRole.UserRole)
                dialog.accept()
                self.open_friend(uid)
        table.cellClicked.connect(open_row)
        table.itemActivated.connect(lambda item: open_row(item.row()))
        self.collection_dialog = dialog
        dialog.finished.connect(lambda _: setattr(self, 'collection_dialog', None))
        dialog.show()

    def build_groups(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        frame, content = card('用标签整理好友', '一位好友可以拥有多个标签。编辑资料时点击标签选择框，可检索、选择或新建标签；删除标签不会删除好友。')
        content.addWidget(button('新建标签', self.add_group))
        layout.addWidget(frame)
        self.groups_table = QTableWidget(0, 2)
        configure_table(self.groups_table)
        self.groups_table.setHorizontalHeaderLabels(['标签', '好友数'])
        layout.addWidget(self.groups_table, 1)
        actions = QHBoxLayout()
        self.group_open = button('查看好友', self.open_selected_group, True)
        self.group_rename = button('重命名', self.rename_selected_group)
        self.group_dissolve = button('删除标签', self.dissolve_selected_group)
        for item in (self.group_open, self.group_rename, self.group_dissolve):
            actions.addWidget(item)
        actions.addStretch()
        layout.addLayout(actions)
        self.group_empty = label('还没有标签。点击“新建标签”开始整理好友。', 'muted', True)
        layout.addWidget(self.group_empty)
        self.groups_table.itemSelectionChanged.connect(self.group_selection_changed)
        self.groups_table.doubleClicked.connect(self.open_selected_group)
        return page

    def selected_group(self):
        row = self.groups_table.currentRow()
        return self.groups_table.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 else None

    def refresh_group_page(self):
        selected = self.selected_group()
        groups = sorted(self.store.group_counts().items(), key=lambda pair: (not bool(pair[0]), pair[0]))
        self.groups_table.blockSignals(True)
        self.groups_table.setRowCount(len(groups))
        self.groups_table.setCurrentCell(-1, -1)
        for row, (name, count) in enumerate(groups):
            item = QTableWidgetItem(name or '（未标记）')
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip(name or '尚未选择任何标签')
            self.groups_table.setItem(row, 0, item)
            self.groups_table.setItem(row, 1, QTableWidgetItem(str(count)))
            if name == selected:
                self.groups_table.selectRow(row)
        self.groups_table.blockSignals(False)
        self.group_empty.setVisible(not groups)
        self.group_selection_changed()

    def group_selection_changed(self):
        name = self.selected_group()
        self.group_open.setEnabled(name is not None)
        self.group_rename.setEnabled(bool(name))
        self.group_dissolve.setEnabled(bool(name))

    def open_selected_group(self, *_):
        name = self.selected_group()
        if name is not None:
            self.navigate('好友')
            self.set_filters(('', name, '', False, 0))

    def rename_selected_group(self):
        name = self.selected_group()
        if name is not None:
            self.rename_group(name)

    def dissolve_selected_group(self):
        name = self.selected_group()
        if name:
            self.dissolve_group(name)

    def add_group(self):
        name, ok = QInputDialog.getText(self, '新建标签', '标签名称：')
        if ok and name.strip():
            self.start_task('create_label', (name.strip(),),
                            success=lambda _: self.notify('标签已创建，可在好友资料中选择。'), text='正在创建标签…')

    def build_statistics(self):
        self.stats_tabs = QTabWidget()
        self.stats_layouts = {}
        self._played_statistics = set()
        self.stats_charts = {}
        for title in ('标签', '年龄', '兴趣', '生日月份'):
            page, layout = scroll_content()
            self.stats_layouts[title] = layout
            self.stats_tabs.addTab(page, title)
        return self.stats_tabs

    def refresh_statistics(self):
        data = self.store.overview()
        modes = {key: chart.choice.currentIndex() for key, chart in self.stats_charts.items()}
        order = ['0–17 岁', '18–29 岁', '30–44 岁', '45–59 岁', '60 岁及以上', '年龄段不确定', '出生年份未知']
        plots = {
            '年龄': ('年龄分布', [(k, data['ages'].get(k, 0)) for k in order],
                '依据当前日期及已知出生年份、月份计算可能年龄范围。仅当整个范围属于同一年龄段时计入，否则计为“年龄段不确定”；出生年份缺失单列未知。没有补造出生日期。'),
            '兴趣': ('兴趣分布', data['interests'].most_common(),
                f"兴趣按逗号、顿号、分号或换行拆分；同一好友的相同兴趣仅计一次，可计入多个类别。{data['interests_unknown']} 位未填写兴趣，不用标签代替兴趣。"),
            '标签': ('各标签人数', [(k or '（未标记）', v) for k, v in data['groups'].most_common()],
                '每位好友按拥有的标签分别计数，可计入多个标签；没有标签的好友单列“未标记”。图例比例按所有标签归属次数计算，相加为 100%；回收站档案不计入。'),
            '生日月份': ('生日月份', [(f'{m} 月', data['months'].get(m, 0)) for m in range(1, 13)] + [('月份未知', data['month_unknown'])],
                '只有 YYYY-MM 格式计入相应月份；仅年份或出生信息为空的档案计入“月份未知”。')}
        for key, (title, values, description) in plots.items():
            layout = self.stats_layouts[key]
            clear_layout(layout)
            frame, content = card(title, f"统计范围：全部 {data['total']} 位有效好友")
            chart = DistributionChart(values, key, self._played_statistics)
            chart.choice.setCurrentIndex(modes.get(key, 0))
            self.stats_charts[key] = chart
            content.addWidget(chart)
            layout.addWidget(frame)
            layout.addWidget(label(description, 'muted', True))
            layout.addStretch()

    def build_data_page(self):
        page, layout = scroll_content()
        for title, subtitle, actions in [
            ('导入与导出好友', 'JSON 包含照片、自定义属性和原始顺序。导入只追加新 ID，已存在 ID 跳过；导出范围为全部有效好友，不受当前筛选影响。',
             [('导入 JSON', self.import_data), ('导出有效好友', lambda: self.export_data(False))]),
            ('完整备份', '完整保存有效好友、照片、自定义属性、顺序及回收站。备份为明文 JSON，请保存在可信位置。主题设置独立保存在数据目录。',
             [('保存完整备份', self.backup)]),
            ('恢复整个数据集', '这与导入不同：恢复将替换当前有效好友、回收站与顺序。程序会先验证文件，并自动生成恢复前备份；任何一步失败都会停止恢复。',
             [('选择备份并恢复…', self.recover)])]:
            frame, content = card(title, subtitle)
            row = QHBoxLayout()
            for name, callback in actions:
                row.addWidget(button(name, callback))
            row.addStretch()
            content.addLayout(row)
            layout.addWidget(frame)
        layout.addWidget(label('导入文件格式：好友档案 JSON。导入和恢复前均会检查文件内容。', 'muted', True))
        layout.addStretch()
        return page

    def build_settings(self):
        page, layout = scroll_content()
        frame, content = card('外观', '主题会保存在当前数据目录，下次打开自动恢复。')
        self.theme_choice = QComboBox()
        self.theme_choice.addItems(['浅色', '深色'])
        self.theme_choice.setCurrentIndex(int(self.dark))
        self.theme_choice.currentIndexChanged.connect(lambda index: self.set_theme(bool(index)))
        content.addWidget(self.theme_choice)
        self.reduce_motion = QCheckBox('减少动态效果（关闭点击波纹、图表入场与弹性动画）')
        self.reduce_motion.setChecked(bool(self.property('reduceMotion')))
        self.reduce_motion.toggled.connect(self.set_reduce_motion)
        content.addWidget(self.reduce_motion)
        layout.addWidget(frame)
        frame, content = card('数据位置', '源码与项目内 exe 共用项目 data 文件夹。单独复制运行版时使用 exe 同级 data；可用 --data-dir 指定其他目录。')
        location = label(str(self.store.path.parent.resolve()), '', True)
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content.addWidget(location)
        row = QHBoxLayout()
        row.addWidget(button('打开数据文件夹', self.open_data_folder))
        row.addWidget(button('刷新磁盘数据', self.reload))
        row.addStretch()
        content.addLayout(row)
        layout.addWidget(frame)
        frame, content = card('关于档案', '完全本地运行，无账号、无同步服务。出生信息允许不完整。保存、导入和恢复均由业务层事务处理。')
        content.addWidget(label('当前格式未记录创建时间、更新时间或联系行为，因此不展示这些指标。', 'muted', True))
        layout.addWidget(frame)
        layout.addStretch()
        return page

    def open_data_folder(self):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.path.parent.resolve()))):
            self.notify('无法打开文件夹，请复制上方路径手动打开。', error=True)

    def build_teaching(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label('直接读取真实节点连接。好友日常操作无需理解这些内部结构。', 'muted', True))
        self.links_table = QTableWidget(0, 4)
        configure_table(self.links_table)
        self.links_table.setHorizontalHeaderLabels(['prev → ID', '节点 ID', '好友', 'next → ID'])
        self.links_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.links_table, 1)
        layout.addWidget(label('HEAD.prev = NULL，TAIL.next = NULL。定位和指针改动平均 O(1)，遍历 O(n)。\n持久化采用候选链表与完整快照，一次保存总体 O(n + t + S)，t 为回收站数量，S 为数据大小。显示排序不改节点连接。', 'muted', True))
        return page

    def refresh_teaching(self):
        rows = self.store.connection_rows()
        self.links_table.setRowCount(len(rows))
        for row, (prev, uid, name, next_) in enumerate(rows):
            for col, text in enumerate((prev or 'NULL ← HEAD', uid, name or '未命名好友', next_ or 'TAIL → NULL')):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.links_table.setItem(row, col, item)
