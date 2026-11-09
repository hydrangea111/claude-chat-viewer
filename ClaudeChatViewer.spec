# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['chat_export.py'],
    pathex=[],
    binaries=[],
    datas=[('ui.html', '.'), ('app.ico', '.')],
    hiddenimports=['export', 'core', 'voice'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# exe 가 압축을 푸는 동안(수 초~수십 초) 먼저 보이는 '여는 중' 안내 창
# 안내 창을 끌어서 옮길 수 있게 하고(제목줄이 없어서 직접 처리), 다른 창이 위로 올라올 수 있게 항상 위는 끈다
class DragSplash(Splash):
    def generate_script(self):
        script = super().generate_script()
        script += """
bind .root.canvas <ButtonPress-1> {set ::dragx [expr {%X-[winfo rootx .]}]; set ::dragy [expr {%Y-[winfo rooty .]}]}
bind .root.canvas <B1-Motion> {wm geometry . +[expr {%X-$::dragx}]+[expr {%Y-$::dragy}]}
.root.canvas configure -cursor fleur
# spinner + sweeping bar (ASCII only: the bootloader cuts the script by character count)
.root.canvas create oval 624 74 664 114 -outline #e6ded1 -width 5 -tags spin_t
.root.canvas create arc 624 74 664 114 -style arc -start 90 -extent 110 -outline #c8643c -width 5 -tags spin
.root.canvas create rectangle 0 190 700 195 -fill #ece5d9 -outline "" -tags bar_t
.root.canvas create rectangle -150 190 0 195 -fill #c8643c -outline "" -tags bar
set ::ccv_ang 90
set ::ccv_bx -150
proc ccv_tick {} {
  incr ::ccv_ang -12
  .root.canvas itemconfigure spin -start $::ccv_ang
  incr ::ccv_bx 10
  if {$::ccv_bx > 700} {set ::ccv_bx -150}
  .root.canvas coords bar $::ccv_bx 190 [expr {$::ccv_bx + 150}] 195
  after 30 ccv_tick
}
ccv_tick
"""
        with open(self.script_name, "w", encoding="utf-8") as fh:
            fh.write(script)
        return script


splash = DragSplash('splash.png', binaries=a.binaries, datas=a.datas, text_pos=None, always_on_top=False)

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
