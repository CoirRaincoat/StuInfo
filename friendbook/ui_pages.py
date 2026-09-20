"""Overview, groups, statistics and utilities; all metrics come from Store."""
from datetime import date
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTableWidget,
    QTableWidgetItem, QComboBox, QInputDialog, QTabWidget, QHeaderView)
from .ui_widgets import label, button, card, scroll_content, clear_layout, BarChart, configure_table


class Pages:
    def build_home(self):
        page, self.home_layout = scroll_content()
        return page

    def refresh_home(self):
        clear_layout(self.home_layout)
        data = self.store.overview()
        metrics = QGridLayout()
        for i, (title, value, note) in enumerate([
                ('好友', data['total'], '全部有效档案'),
                ('本月生日', len(data['birthdays']), f"仅统计已知月份 · {data['month_unknown']} 位月份未知"),
                ('收藏', data['favorites'], '留在身边的重要伙伴'),
                ('分组', sum(bool(k) for k in data['groups']), '不含未分组')]):
            frame, content = card()
            content.addWidget(label(title, 'muted'))
            content.addWidget(label(str(value), 'metric'))
            content.addWidget(label(note, 'muted', True))
            metrics.addWidget(frame, i // 2, i % 2)
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
            content.addWidget(label(f"此处展示前 6 位，共 {len(data['birthdays'])} 位；完整月份分布见统计页面。", 'muted', True))
        self.home_layout.addWidget(frame)
        frame, content = card('分组一览', '按全部有效好友统计')
        content.addWidget(BarChart([(name or '（未分组）', count) for name, count in data['groups'].most_common(6)]))
        content.addWidget(button('管理分组', lambda: self.navigate('分组')))
        self.home_layout.addWidget(frame)
        self.home_layout.addStretch()

    def build_groups(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        frame, content = card('以关系整理好友', '分组随好友资料建立。编辑好友时可以直接输入自定义分组；解散分组不会删除好友。')
        content.addWidget(button('添加好友到新分组', self.add_group))
        layout.addWidget(frame)
        self.groups_table = QTableWidget(0, 2)
        configure_table(self.groups_table)
        self.groups_table.setHorizontalHeaderLabels(['分组', '好友数'])
        layout.addWidget(self.groups_table, 1)
        actions = QHBoxLayout()
        self.group_open = button('查看组内好友', self.open_selected_group, True)
        self.group_rename = button('重命名', self.rename_selected_group)
        self.group_dissolve = button('解散分组', self.dissolve_selected_group)
        for item in (self.group_open, self.group_rename, self.group_dissolve):
            actions.addWidget(item)
        actions.addStretch()
        layout.addLayout(actions)
        self.group_empty = label('还没有分组。在好友资料中填写分组即可开始整理。', 'muted', True)
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
            item = QTableWidgetItem(name or '（未分组）')
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip(name or '没有填写分组')
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
        self.group_rename.setEnabled(name is not None)
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
        name, ok = QInputDialog.getText(self, '新分组', '为新好友指定一个分组（保存好友后建立）：')
        if ok and name.strip():
            self.navigate('好友')
            self.add(group=name.strip())

    def build_statistics(self):
        self.stats_tabs = QTabWidget()
        self.stats_layouts = {}
        for title in ('年龄', '兴趣', '分组', '生日月份'):
            page, layout = scroll_content()
            self.stats_layouts[title] = layout
            self.stats_tabs.addTab(page, title)
        return self.stats_tabs

    def refresh_statistics(self):
        data = self.store.overview()
        order = ['0–17 岁', '18–29 岁', '30–44 岁', '45–59 岁', '60 岁及以上', '年龄段不确定', '出生年份未知']
        plots = {
            '年龄': ('年龄分布', [(k, data['ages'].get(k, 0)) for k in order],
                '依据当前日期及已知出生年份、月份计算可能年龄范围。仅当整个范围属于同一年龄段时计入，否则计为“年龄段不确定”；出生年份缺失单列未知。没有补造出生日期。'),
            '兴趣': ('兴趣分布', data['interests'].most_common(),
                f"兴趣按逗号、顿号、分号或换行拆分；同一好友的相同兴趣仅计一次，可计入多个类别。{data['interests_unknown']} 位未填写兴趣，不用标签代替兴趣。"),
            '分组': ('分组人数', [(k or '（未分组）', v) for k, v in data['groups'].most_common()],
                '每位有效好友计入一个分组，空分组单列。回收站档案不计入统计。'),
            '生日月份': ('生日月份', [(f'{m} 月', data['months'].get(m, 0)) for m in range(1, 13)] + [('月份未知', data['month_unknown'])],
                '只有 YYYY-MM 格式计入相应月份；仅年份或出生信息为空的档案计入“月份未知”。')}
        for key, (title, values, description) in plots.items():
            layout = self.stats_layouts[key]
            clear_layout(layout)
            frame, content = card(title, f"统计范围：全部 {data['total']} 位有效好友")
            content.addWidget(BarChart(values))
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
