"""Resolve storage independently of the shell's working directory."""
from pathlib import Path
import sys


def default_data_dir():
    if not getattr(sys, 'frozen', False):
        return Path(__file__).resolve().parents[1] / 'data'
    executable_dir = Path(sys.executable).resolve().parent
    # Standard project build: <project>/dist/Friendbook/Friendbook.exe.
    project = executable_dir.parent.parent
    if (executable_dir.parent.name == 'dist'
            and (project / 'main.py').is_file()
            and (project / 'Friendbook.spec').is_file()
            and (project / 'friendbook' / 'linked.py').is_file()):
        return project / 'data'
    # A distribution copied away from the source tree is portable.
    return executable_dir / 'data'
