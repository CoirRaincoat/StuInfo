from pathlib import Path
import sys
from friendbook.paths import default_data_dir


def test_source_path_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.chdir(tmp_path)
    assert default_data_dir() == Path(__file__).resolve().parents[1] / 'data'


def test_project_executable_uses_project_data(tmp_path, monkeypatch):
    (tmp_path / 'friendbook').mkdir()
    for name in ('main.py', 'Friendbook.spec', 'friendbook/linked.py'):
        (tmp_path / name).touch()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'dist' / 'Friendbook' / 'Friendbook.exe'))
    assert default_data_dir() == tmp_path / 'data'


def test_portable_executable_uses_local_data(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'Friendbook.exe'))
    assert default_data_dir() == tmp_path / 'data'
