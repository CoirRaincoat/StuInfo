"""Verify the packaged Windows GUI starts twice and preserves a populated database."""
from pathlib import Path
import copy
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from friendbook.core import Store

root = Path(__file__).resolve().parents[1]
folder = root / '.test-data' / 'exe-populated'
store = Store(folder / 'friends.sqlite3')
store.import_file(root / 'demo' / '虚构好友档案.json')
before = copy.deepcopy(store.payload())
store.close()
exe = root / 'dist' / 'Friendbook' / 'Friendbook.exe'
for attempt in range(2):
    result = subprocess.run([str(exe), '--data-dir', str(folder), '--smoke-test'], timeout=30)
    if result.returncode:
        raise SystemExit(f'Packaged GUI failed with code {result.returncode}')
    reopened = Store(folder / 'friends.sqlite3')
    assert reopened.payload() == before, 'Packaged launch changed persisted records'
    assert reopened.book.validate()
    reopened.close()
    print(f'Packaged Windows launch {attempt + 1}: exit 0; 12 fictional records, photos and order preserved.')
