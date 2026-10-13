# Windows directory build; user data are never stored in this distribution.
a = Analysis(['main.py'], pathex=[], binaries=[], datas=[], hiddenimports=[],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['tkinter'], noarchive=False)
# PyInstaller can discover an unrelated ICU runtime from the build machine's
# DLL search paths. The pinned Windows PySide wheel uses Windows' ICU, so do
# not let a developer-tool ICU (e.g. Poppler's) shadow it inside the bundle.
a.binaries = [entry for entry in a.binaries
              if entry[0].replace('\\', '/').rsplit('/', 1)[-1].lower()
              not in {'icuuc.dll', 'icuin.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Friendbook',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Friendbook')
