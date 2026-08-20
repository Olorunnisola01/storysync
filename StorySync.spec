# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('C:\\Windows\\Fonts\\georgiab.ttf', 'fonts'), ('C:\\Windows\\Fonts\\georgia.ttf', 'fonts'), ('C:\\Windows\\Fonts\\timesbd.ttf', 'fonts'), ('C:\\Windows\\Fonts\\times.ttf', 'fonts'), ('C:\\Windows\\Fonts\\NotoSerif-Bold.ttf', 'fonts'), ('C:\\Windows\\Fonts\\NotoSerif-Regular.ttf', 'fonts'), ('C:\\Windows\\Fonts\\cambriab.ttf', 'fonts'), ('C:\\Windows\\Fonts\\BKANT.TTF', 'fonts'), ('C:\\Windows\\Fonts\\courbd.ttf', 'fonts'), ('C:\\Windows\\Fonts\\cour.ttf', 'fonts')]
datas += collect_data_files('customtkinter')


a = Analysis(
    ['storysync.py'],
    pathex=[],
    binaries=[('assets\\ffmpeg.exe', '.'), ('assets\\ffprobe.exe', '.')],
    datas=datas,
    hiddenimports=['storysync', 'storysync.gui', 'storysync.transcription', 'storysync.render'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='StorySync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
