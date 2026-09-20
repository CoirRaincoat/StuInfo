"""Verify default packaged storage without printing personal record contents."""
from pathlib import Path
import sqlite3
import subprocess
import time

root = Path(__file__).resolve().parents[1]
database = root / 'data' / 'friends.sqlite3'
lock = root / 'data' / 'app.lock'


def snapshot():
    connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    try:
        return connection.execute('SELECT revision,payload FROM state WHERE id=1').fetchone()
    finally:
        connection.close()


before = snapshot()
process = subprocess.Popen([str(root / 'dist' / 'Friendbook' / 'Friendbook.exe'), '--smoke-test'],
                           cwd=root / '.test-data')
observed = False
deadline = time.monotonic() + 20
while process.poll() is None and time.monotonic() < deadline:
    if lock.exists():
        try:
            observed = int(lock.read_text(encoding='utf-8').splitlines()[0]) == process.pid
        except (OSError, ValueError, IndexError):
            pass
        if observed:
            break
    time.sleep(.05)
assert process.wait(timeout=25) == 0
assert observed, 'Packaged process did not lock the project data directory'
assert snapshot() == before, 'Launch changed the saved data'
print('Verified: default EXE uses project/data from another working directory; exit 0; data unchanged.')
