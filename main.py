import argparse
from pathlib import Path
import sys
from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from friendbook.core import Store
from friendbook.gui import Window
from friendbook.paths import default_data_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, help='指定独立数据目录')
    parser.add_argument('--smoke-test', action='store_true', help='显示窗口后自动退出，仅供构建验证')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setStyle('Fusion')
    folder = args.data_dir or default_data_dir()
    store = None
    try:
        folder.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(folder / 'app.lock'))
        lock.setStaleLockTime(0)
        if not lock.tryLock(100):
            raise ValueError('该数据目录已由另一窗口使用，请切换到已打开的好友档案窗口。')
        store = Store(folder / 'friends.sqlite3')
        window = Window(store)
        window.show()
        if args.smoke_test:
            QTimer.singleShot(1200, app.quit)
        result = app.exec()
        store.close()
        lock.unlock()
        return result
    except Exception:
        if store:
            store.close()
        QMessageBox.critical(None, '无法打开好友档案', '启动失败：数据目录被占用、无法写入或数据库损坏。\n原文件不会被自动删除。请检查数据目录，或用 --data-dir 指定新目录，再从备份恢复。\n数据目录：' + str(folder))
        return 1


if __name__ == '__main__':
    sys.exit(main())
