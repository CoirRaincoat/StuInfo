"""Reproducible Qt interaction captures; isolated fictional data only.

On Linux: QT_QPA_PLATFORM=offscreen python scripts/visual_interactions.py
Pass --font /path/to/CJK-font.otf if the host lacks Chinese fonts.
"""
import argparse
import os
from pathlib import Path
import sys
import tempfile
import time

if os.name != 'nt':
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from friendbook.core import Store
from friendbook.gui import Window


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--font', type=Path)
    parser.add_argument('--out', type=Path, default=Path('docs/screenshots/interactions'))
    parser.add_argument('--screens', nargs='*', help='Only save these captures, still exercise every flow')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyle('Fusion')
    if args.font and QFontDatabase.addApplicationFont(str(args.font)) < 0:
        raise RuntimeError('Could not load requested font')
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='friendbook-interactions-') as folder:
        store = Store(Path(folder) / 'fictional.sqlite3')
        store.import_file(root / 'demo/虚构好友档案.json')
        records = store.records()
        record = records[1]
        record.update(contacts={'电话1': 'demo-001', '电话2': 'demo-002', 'QQ': 'demo-qq',
                                '微信': 'demo-wechat', '邮箱': 'demo@example.invalid'},
                      custom={'籍贯': '浙江 · 虚构地点', '职业': '虚构职业'})
        store.save(record, expected=record['version'])
        window = Window(store)
        window.resize(1280, 820)
        window.show()

        def capture(name, settle=400):
            app.processEvents()
            QTest.qWait(settle)
            if not args.screens or name in args.screens:
                assert window.grab().save(str(args.out / (name + '.png')))

        for dark in (False, True):
            suffix = 'dark' if dark else 'light'
            window.set_theme(dark)
            window.navigate('好友')
            window.back_to_list()
            capture('list-' + suffix)
            assert not window.detail_panel.isVisible()
            window.management_button.click()
            window.toggle_friend_check(records[0]['id'])
            window.toggle_friend_check(records[2]['id'])
            capture('manage-' + suffix)
            table = window.table
            start = table.visualItemRect(table.item(0, 4)).center()
            QTest.mousePress(table.viewport(), Qt.MouseButton.LeftButton, pos=start)
            expected = [records[0]['id'], records[2]['id']]
            assert table._pressed_handle == records[0]['id'], 'Handle press was not accepted'
            until = time.monotonic() + 2
            while not table._drag_ids and table._pressed_handle is not None and time.monotonic() < until:
                QTest.qWait(10)
            assert table._drag_ids == expected, 'Long press did not start the expected multi-friend drag'
            end = table.visualItemRect(table.item(3, 4)).bottomLeft() + QPoint(15, -2)
            QTest.mouseMove(table.viewport(), end)
            capture('drag-' + suffix, 120)
            QTest.keyClick(table, Qt.Key.Key_Escape)
            QTest.mouseRelease(table.viewport(), Qt.MouseButton.LeftButton, pos=end)
            assert [r['id'] for r in store.records()] == [r['id'] for r in records]
            window.set_management(False)
            window.select_uid(record['id'])
            capture('drawer-' + suffix)
            window.edit()
            window.editor.tabs.setCurrentIndex(1)
            capture('contacts-' + suffix)
            window.editor.tabs.setCurrentIndex(0)
            capture('profile-' + suffix)
            window.discard_editor()
            window.navigate('概览')
            capture('home-' + suffix)
        window.set_theme(False)
        for width, height in ((900, 650), (820, 580)):
            window.resize(width, height)
            window.navigate('好友')
            window.back_to_list()
            capture(f'compact-{width}')
            window.management_button.click()
            capture(f'manage-{width}')
            window.set_management(False)
            window.select_uid(record['id'])
            capture(f'drawer-{width}')
            window.navigate('概览')
            capture(f'home-{width}')
        window.close()
        store.close()
    print(f'Qt navigation, management, drag/cancel, drawers and contacts checked: {args.out}')


if __name__ == '__main__':
    main()
