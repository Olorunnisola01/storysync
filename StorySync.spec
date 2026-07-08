# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

_F = 'C:\\Windows\\Fonts\\'
datas = [
    # Serif / Classic (Windows standard — bundled for portability)
    (_F + 'georgiab.ttf',   'fonts'), (_F + 'georgia.ttf',   'fonts'),
    (_F + 'timesbd.ttf',    'fonts'), (_F + 'times.ttf',     'fonts'),
    (_F + 'cambriab.ttf',   'fonts'),
    (_F + 'BKANT.TTF',      'fonts'),
    (_F + 'GARABD.TTF',     'fonts'), (_F + 'GARA.TTF',      'fonts'),
    (_F + 'palab.ttf',      'fonts'), (_F + 'pala.ttf',      'fonts'),
    (_F + 'constanb.ttf',   'fonts'), (_F + 'constan.ttf',   'fonts'),
    (_F + 'BOOKOSB.TTF',    'fonts'), (_F + 'BOOKOS.TTF',    'fonts'),
    # Noto Serif (may not exist on all Windows installs)
    (_F + 'NotoSerif-Bold.ttf',     'fonts'), (_F + 'NotoSerif-Regular.ttf',     'fonts'),
    # Sans-Serif (Windows standard)
    (_F + 'arialbd.ttf',    'fonts'), (_F + 'arial.ttf',     'fonts'),
    (_F + 'calibrib.ttf',   'fonts'), (_F + 'calibri.ttf',   'fonts'),
    (_F + 'verdanab.ttf',   'fonts'), (_F + 'verdana.ttf',   'fonts'),
    (_F + 'trebucbd.ttf',   'fonts'), (_F + 'trebuc.ttf',    'fonts'),
    (_F + 'tahomabd.ttf',   'fonts'), (_F + 'tahoma.ttf',    'fonts'),
    (_F + 'segoeuib.ttf',   'fonts'), (_F + 'segoeui.ttf',   'fonts'),
    (_F + 'Candarab.ttf',   'fonts'), (_F + 'Candara.ttf',   'fonts'),
    (_F + 'corbelb.ttf',    'fonts'), (_F + 'corbel.ttf',    'fonts'),
    (_F + 'courbd.ttf',     'fonts'), (_F + 'cour.ttf',      'fonts'),
    (_F + 'comicbd.ttf',    'fonts'), (_F + 'comic.ttf',     'fonts'),
    # Non-standard / Google fonts (must bundle)
    (_F + 'NotoSans-Bold.ttf',       'fonts'), (_F + 'NotoSans-Regular.ttf',       'fonts'),
    (_F + 'Roboto-Bold.ttf',         'fonts'), (_F + 'Roboto-Regular.ttf',         'fonts'),
    (_F + 'Lato-Bold.ttf',           'fonts'), (_F + 'Lato-Regular.ttf',           'fonts'),
    (_F + 'Montserrat-Bold.ttf',     'fonts'), (_F + 'Montserrat-Regular.ttf',     'fonts'),
    (_F + 'OpenSans-Bold.ttf',       'fonts'), (_F + 'OpenSans-Regular.ttf',       'fonts'),
    (_F + 'Raleway-Bold.ttf',        'fonts'), (_F + 'Raleway-Regular.ttf',        'fonts'),
    (_F + 'SourceSansPro-Bold.ttf',  'fonts'), (_F + 'SourceSansPro-Regular.ttf',  'fonts'),
    (_F + 'CormorantInfant-Bold.ttf','fonts'), (_F + 'CormorantInfant-Regular.ttf','fonts'),
]
datas += collect_data_files('customtkinter')


a = Analysis(
    ['storysync.py'],
    pathex=[],
    binaries=[],
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
