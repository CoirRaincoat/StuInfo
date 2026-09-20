"""Render native Windows Qt pages using only isolated, fictional records."""
import os
if os.name != 'nt':
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from friendbook.core import Store
from friendbook.gui import Window

root = Path(__file__).resolve().parents[1]
out = root / 'docs' / 'screenshots'
out.mkdir(parents=True, exist_ok=True)
(root / '.test-data').mkdir(exist_ok=True)
folder = Path(tempfile.mkdtemp(prefix='visual-upgrade-', dir=root / '.test-data'))
app = QApplication([])
app.setStyle('Fusion')
store = Store(folder / 'friends.sqlite3')
store.import_file(root / 'demo' / '虚构好友档案.json')
window = Window(store)
window.resize(1280, 820)
window.show()
captures = 0


def capture(name):
    global captures
    app.processEvents()
    QTest.qWait(100)
    assert window.grab().save(str(out / (name + '.png')))
    captures += 1


for dark in (False, True):
    window.set_theme(dark)
    suffix = 'dark' if dark else 'light'
    for page, filename in [('好友', 'friends'), ('概览', 'home'), ('分组', 'groups'),
                            ('统计', 'stats'), ('导入与备份', 'data'), ('回收站', 'trash'),
                            ('设置', 'settings'), ('链表教学', 'teaching')]:
        # Exercise actual native Qt navigation hit targets, not offscreen painting.
        index = window.PAGE_NAMES.index(page)
        QTest.mouseClick(window.nav.viewport(), Qt.MouseButton.LeftButton,
                         pos=window.nav.visualItemRect(window.nav.item(index)).center())
        app.processEvents()
        assert window.page_name == page
        if page == '好友':
            QTest.mouseClick(window.table.viewport(), Qt.MouseButton.LeftButton,
                             pos=window.table.visualItemRect(window.table.item(0, 0)).center())
        capture(f'{filename}-{suffix}')
    window.navigate('好友')
    window.table.selectRow(0)
    QTest.mouseClick(window.edit_button, Qt.MouseButton.LeftButton)
    assert window.editor and not window.editor.isWindow()
    capture(f'editor-{suffix}')
    window.editor.tabs.setCurrentIndex(2)
    capture(f'custom-{suffix}')
    window.discard_editor()

# Real native edit → background transaction → detail round trip, fictional only.
window.set_theme(False)
window.navigate('好友')
window.table.selectRow(1)
uid = window.selected()
QTest.mouseClick(window.edit_button, Qt.MouseButton.LeftButton)
window.editor.notes.setPlainText('完全虚构的交互验证备注，测试后不进入用户数据。')
QTest.mouseClick(window.editor.save_button, Qt.MouseButton.LeftButton)
deadline = time.monotonic() + 15
while (window._busy or window._tasks) and time.monotonic() < deadline:
    app.processEvents()
    QTest.qWait(10)
assert not window._busy and window.editor is None
assert store.record(uid)['notes'].startswith('完全虚构的交互验证备注')
window.notice.hide()
window.resize(900, 650)
window.select_uid(uid)
capture('compact-detail')
window.edit()
capture('compact-editor')
window.editor.fields['birth'].setText('2000-13')
QTest.mouseClick(window.editor.save_button, Qt.MouseButton.LeftButton)
assert window.editor.error.isVisible()
capture('invalid-input')
window.discard_editor()
window.back_to_list()
capture('compact-list')
window.resize(1280, 820)
window.toggle_filters()
window.sort.setCurrentIndex(1)
capture('filters-light')
window.query.setFocus()
QTest.keyClicks(window.query, 'no-matching-record')
QTest.qWait(300)
assert window.table.rowCount() == 0
capture('no-results')
window.set_filters(('', None, '', False, 0))
window.filters_widget.hide()
window.select_uid(store.records()[0]['id'])
capture('light')
window.set_theme(True)
capture('dark')
window.edit()
capture('editor')
window.discard_editor()
window.navigate('统计')
for index, name in ((1, 'interests'), (2, 'groups'), (3, 'birth-months')):
    window.stats_tabs.setCurrentIndex(index)
    capture('stats-' + name)
window.close()
store.close()
print(f'Native Qt navigation, inline edit/save and {captures} screenshots verified using fictional data only.')
