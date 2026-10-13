"""Native Qt review captures using isolated fictional records only."""
import os
from pathlib import Path
import sys
import tempfile
import time
from contextlib import ExitStack

if os.name != 'nt':
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QInputDialog, QTableWidget
from PySide6.QtTest import QTest
from friendbook.core import Store
from friendbook.gui import Window


def wait_for(predicate):
    until = time.monotonic() + 5
    while not predicate():
        if time.monotonic() >= until:
            raise AssertionError('Native GUI did not reach expected state')
        QTest.qWait(10)


def main():
    out = ROOT / 'docs/screenshots/review-20260927'
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyle('Fusion')
    with tempfile.TemporaryDirectory(prefix='friendbook-review-') as folder, ExitStack() as cleanup:
        store = Store(Path(folder) / 'fictional.sqlite3')
        cleanup.callback(store.close)
        store.import_file(ROOT / 'demo/虚构好友档案.json')
        original = store.payload()
        window = Window(store)
        cleanup.callback(window.close)
        window.resize(1280, 820)
        window.show()

        def capture(name, widget=None):
            app.processEvents()
            QTest.qWait(120)
            assert (widget or window).grab().save(str(out / f'{name}.png'))

        for dark in (False, True):
            window.set_theme(dark)
            suffix = 'dark' if dark else 'light'
            window.navigate('统计')
            window.stats_tabs.setCurrentIndex(0)
            app.processEvents()
            chart = window.stats_charts['标签']
            chart.choice.setCurrentIndex(0)
            wait_for(lambda: chart.canvas.progress == 1.)
            point = chart.canvas.bar_rects()[0][2].center().toPoint()
            QTest.mouseMove(chart.canvas, point)
            capture('chart-hover-' + suffix)
            QTest.mouseClick(chart.canvas, Qt.MouseButton.LeftButton, pos=point)
            assert window.collection_dialog
            table = window.collection_dialog.findChild(QTableWidget)
            assert table.rowCount() == chart.counts[0][1]
            capture('chart-friends-' + suffix, window.collection_dialog)
            window.collection_dialog.close()
            chart.choice.setCurrentIndex(1)
            wait_for(lambda: chart.canvas.progress == 1.)
            capture('chart-donut-' + suffix)
            chart.export_png(out / f'export-donut-{suffix}.png', '标签分布',
                             '虚构演示数据 · 12 位有效好友', '每位好友按各标签计数，比例以归属次数为分母。')
            window.open_quality_statistics()
            wait_for(lambda: window.stats_charts['资料检查'].canvas.progress == 1.)
            capture('quality-' + suffix)
            window.navigate('概览')
            capture('home-' + suffix)

        window.set_theme(False)
        window.navigate('好友')
        window.filters_widget.show()
        window.query.setText('阅读')
        # Save immediately, before the search debounce finishes.
        def name_dialog():
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, QInputDialog)
            dialog.setTextValue('阅读伙伴')
            dialog.accept()
        QTimer.singleShot(60, name_dialog)
        window.save_view_button.click()
        assert len(window._saved_views) == 1
        window.set_filters(('', None, '', False, 0))
        window.saved_views_choice.setCurrentIndex(1)
        window.apply_view_button.click()
        assert window._filters[0] == '阅读'
        capture('saved-view-light')
        window.set_filters(('', None, '', False, 0))
        for width, height in ((900, 650), (820, 580)):
            window.resize(width, height)
            capture(f'filters-{width}')
            window.navigate('统计')
            window.stats_tabs.setCurrentIndex(0)
            window.set_reduce_motion(True)
            chart = window.stats_charts['标签']
            chart.choice.setCurrentIndex(1)
            capture(f'chart-{width}')
            assert chart.canvas.progress == 1.
            window.navigate('好友')
        assert store.payload() == original, 'Read-only review changed fictional friend records'
    print(f'Native Qt charts, drill-down, named filters, themes and small windows verified: {out}')


if __name__ == '__main__':
    main()
