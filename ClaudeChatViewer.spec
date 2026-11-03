# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['chat_export.py'],
    pathex=[],
    binaries=[],
    datas=[('ui.html', '.'), ('app.ico', '.')],
    hiddenimports=['export', 'core'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# exe 가 압축을 푸는 동안(수 초~수십 초) 먼저 보이는 '여는 중' 안내 창
splash = Splash('splash.png', binaries=a.binaries, datas=a.datas, text_pos=None, always_on_top=True)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    splash,
    splash.binaries,
    [],
    name='ClaudeChatViewer',
    icon='app.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
