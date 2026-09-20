"""One-time, non-destructive migration from the old user directory.

Close Friendbook before running. Existing destination data are never overwritten.
"""
import ctypes
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from friendbook.core import Store


def migrate():
    source = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Friendbook'
    destination = root / 'data'
    if destination.exists():
        raise RuntimeError('Destination already exists; no files were overwritten.')
    if not (source / 'friends.sqlite3').is_file():
        raise RuntimeError('No legacy database found.')
    # Read the old Qt lock without changing the source directory.
    lock = source / 'app.lock'
    if lock.exists() and os.name == 'nt':
        pid = int(lock.read_text(encoding='utf-8').splitlines()[0])
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if handle:
            kernel.CloseHandle(handle)
            raise RuntimeError('Legacy application is still running. Save and close it first.')
        if ctypes.get_last_error() != 87:  # ERROR_INVALID_PARAMETER: PID no longer exists
            raise RuntimeError('Cannot verify that the legacy application has closed.')
    staging = Path(tempfile.mkdtemp(prefix='.friendbook-migration-', dir=root))
    # SQLite backup produces a consistent copy without modifying the original DB.
    old = sqlite3.connect((source / 'friends.sqlite3').as_uri() + '?mode=ro', uri=True)
    new = sqlite3.connect(staging / 'friends.sqlite3')
    try:
        old.backup(new)
        assert new.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert old.execute('SELECT revision,payload FROM state WHERE id=1').fetchone() == new.execute(
            'SELECT revision,payload FROM state WHERE id=1').fetchone()
        raw = new.execute('SELECT payload FROM state WHERE id=1').fetchone()[0]
        book, trash = Store.decode(json.loads(raw))
    finally:
        new.close()
        old.close()
    for item in source.iterdir():
        if item.is_file() and item.name not in {
                'app.lock', 'friends.sqlite3', 'friends.sqlite3-journal',
                'friends.sqlite3-wal', 'friends.sqlite3-shm'}:
            shutil.copy2(item, staging / item.name)
    # On Windows rename fails if destination appears meanwhile; no overwrite.
    staging.rename(destination)
    print('Migration verified: database payload, photos, order and trash preserved.')
    print('Legacy source retained. New directory: ' + str(destination))


if __name__ == '__main__':
    migrate()
