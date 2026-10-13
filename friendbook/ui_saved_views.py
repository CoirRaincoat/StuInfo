"""Named display filters stored separately from friend records in QSettings."""
import json

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QInputDialog, QToolButton, QMenu

from .ui_widgets import button, label


SETTINGS_KEY = 'saved_views'
MAX_VIEWS = 20


def validate_view(name, filters):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
        raise ValueError('视图名称应为 1–60 个字符')
    if not isinstance(filters, (list, tuple)) or len(filters) != 5:
        raise ValueError('视图筛选格式无效')
    query, group, tag, favorites, sort = filters
    if (not isinstance(query, str) or len(query) > 1000 or
            (group is not None and (not isinstance(group, str) or len(group) > 200)) or
            not isinstance(tag, str) or len(tag) > 200 or type(favorites) is not bool or
            type(sort) is not int or sort not in (0, 1, 2)):
        raise ValueError('筛选内容无效或过长：关键词最多 1000 字，标签和备注最多 200 字')
    return {'name': name.strip(), 'filters': list(filters)}


def decode_views(raw):
    if not isinstance(raw, str) or len(raw) > 100000:
        raise ValueError('常用视图设置格式无效或过大')
    values = json.loads(raw)
    if not isinstance(values, list) or len(values) > MAX_VIEWS:
        raise ValueError('常用视图数量超出限制')
    result = []
    names = set()
    for item in values:
        if not isinstance(item, dict) or set(item) != {'name', 'filters'}:
            raise ValueError('常用视图设置格式无效')
        view = validate_view(item['name'], item['filters'])
        if view['name'] in names:
            raise ValueError('常用视图名称重复')
        names.add(view['name'])
        result.append(view)
    return result


class SavedViews:
    def build_saved_views(self):
        try:
            self._saved_views = decode_views(self.settings.value(SETTINGS_KEY, '[]'))
        except (ValueError, TypeError):
            self._saved_views = []
            self.notify('常用视图设置无法读取。好友数据不受影响；重新保存视图可重建这些设置。', error=True)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label('常用视图', 'fieldLabel'))
        self.saved_views_choice = QComboBox()
        self.saved_views_choice.setMinimumWidth(80)
        self.saved_views_choice.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.saved_views_choice.setAccessibleName('选择已保存的筛选视图')
        self.saved_views_choice.setToolTip('保存关键词、标签、备注、收藏条件及临时排序；不改变好友数据或原始顺序')
        layout.addWidget(self.saved_views_choice, 1)
        self.apply_view_button = button('应用', self.apply_saved_view)
        layout.addWidget(self.apply_view_button)
        self.save_view_button = button('保存当前…', self.save_current_view)
        layout.addWidget(self.save_view_button)
        more = QToolButton()
        more.setText('更多')
        more.setAccessibleName('管理已保存的筛选视图')
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        self.update_view_action = menu.addAction('用当前条件更新此视图…', self.update_saved_view)
        self.delete_view_action = menu.addAction('删除此视图…', self.delete_saved_view)
        more.setMenu(menu)
        layout.addWidget(more)
        self.saved_views_choice.currentIndexChanged.connect(self._view_selection_changed)
        self._refresh_saved_views()
        return row

    def _refresh_saved_views(self, selected=None):
        if selected is None:
            selected = self.saved_views_choice.currentData()
        self.saved_views_choice.blockSignals(True)
        self.saved_views_choice.clear()
        self.saved_views_choice.addItem('选择常用视图', None)
        for view in self._saved_views:
            self.saved_views_choice.addItem(view['name'], view['name'])
        self.saved_views_choice.setCurrentIndex(max(0, self.saved_views_choice.findData(selected)))
        self.saved_views_choice.blockSignals(False)
        self._view_selection_changed()

    def _view_selection_changed(self, *_):
        valid = self.saved_views_choice.currentData() is not None
        self.apply_view_button.setEnabled(valid)
        self.update_view_action.setEnabled(valid)
        self.delete_view_action.setEnabled(valid)

    def _selected_view(self):
        name = self.saved_views_choice.currentData()
        return next((view for view in self._saved_views if view['name'] == name), None)

    def _write_saved_views(self, values, selected=None):
        # Validate before writing. A failed settings sync must never report success.
        encoded = json.dumps(values, ensure_ascii=False)
        try:
            validated = decode_views(encoded)
        except (ValueError, TypeError) as exc:
            self.notify(str(exc), error=True)
            return False
        previous = self.settings.value(SETTINGS_KEY, '[]')
        self.settings.setValue(SETTINGS_KEY, encoded)
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            self.settings.setValue(SETTINGS_KEY, previous)
            self.notify('常用视图未保存：无法写入设置文件，请检查数据目录是否可写。', error=True)
            return False
        self._saved_views = validated
        self._refresh_saved_views(selected)
        return True

    def apply_saved_view(self):
        view = self._selected_view()
        if self.page_name != '好友' or self._busy or not view:
            return
        # set_filters also clears checked IDs without discarding a management draft.
        values = tuple(view['filters'])
        self.request_leave(lambda: self.set_filters(values))

    def _with_current_view_filters(self, callback):
        if self.page_name != '好友' or self._busy:
            return
        # Capture controls first: a pending search debounce has not reached _filters yet.
        values = self.filter_values()
        try:
            validate_view('检查', values)
        except ValueError as exc:
            self.notify(str(exc), error=True)
            return
        if values != self._filters:
            def apply_then_continue():
                self.set_filters(values)
                callback(values)
            self.request_leave(apply_then_continue)
        else:
            callback(values)

    def save_current_view(self):
        def save(values):
            name, ok = QInputDialog.getText(self, '保存常用视图', '视图名称（最多 60 字，最多保存 20 个）：')
            if not ok:
                return
            try:
                view = validate_view(name, values)
            except ValueError as exc:
                self.notify(str(exc), error=True)
                return
            existing = next((v for v in self._saved_views if v['name'] == view['name']), None)
            if existing and not self.confirm('更新已有视图', '同名视图已存在，要使用当前筛选条件更新它吗？'):
                return
            if not existing and len(self._saved_views) >= MAX_VIEWS:
                self.notify('最多保存 20 个常用视图，请先删除不再使用的视图。', error=True)
                return
            views = [view if v['name'] == view['name'] else v for v in self._saved_views]
            if not existing:
                views.append(view)
            if self._write_saved_views(views, view['name']):
                self.notify('常用视图已保存；好友数据与原始顺序保持不变。')
        self._with_current_view_filters(save)

    def update_saved_view(self):
        view = self._selected_view()
        if not view:
            return
        def update(values):
            if not self.confirm('更新常用视图', '使用当前关键词、标签、备注、收藏条件及排序替换此视图的设置？'):
                return
            updated = validate_view(view['name'], values)
            if self._write_saved_views([updated if v['name'] == view['name'] else v for v in self._saved_views], view['name']):
                self.notify('常用视图已更新。')
        self._with_current_view_filters(update)

    def delete_saved_view(self):
        view = self._selected_view()
        if self.page_name != '好友' or self._busy or not view:
            return
        if self.confirm('删除常用视图', '仅删除这组保存的筛选条件，好友数据和当前显示条件不会改变。'):
            if self._write_saved_views([v for v in self._saved_views if v['name'] != view['name']]):
                self.notify('常用视图已删除。')
