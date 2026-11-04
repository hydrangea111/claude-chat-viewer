"""소스(pythonw)로 실행할 때 쓰는 '여는 중입니다' 안내 창.
chat_export.py 가 맨 처음에 따로 띄우고, 앱 창이 그려지면 신호 파일을 만들어 닫게 한다.
인자: 신호 파일 경로, 부모 프로세스 PID"""
import os
import sys
import time
import ctypes
import tkinter as tk
from pathlib import Path


def alive(pid):
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE


def main():
    flag, ppid = Path(sys.argv[1]), int(sys.argv[2])
    img = Path(__file__).parent / "splash.png"
    root = tk.Tk()
    root.overrideredirect(True)
    pic = tk.PhotoImage(file=str(img))
    tk.Label(root, image=pic, borderwidth=0).pack()
    root.update_idletasks()
    w, h = pic.width(), pic.height()
    root.geometry("%dx%d+%d+%d" % (w, h, (root.winfo_screenwidth() - w) // 2, (root.winfo_screenheight() - h) // 2))
    drag = {}
    lab = root.winfo_children()[0]
    lab.configure(cursor="fleur")   # 제목줄이 없는 안내 창이라 끌어서 옮길 수 있게 한다
    lab.bind("<ButtonPress-1>", lambda e: drag.update(x=e.x_root - root.winfo_x(), y=e.y_root - root.winfo_y()))
    lab.bind("<B1-Motion>", lambda e: root.geometry("+%d+%d" % (e.x_root - drag["x"], e.y_root - drag["y"])))
    t0 = time.time()

    def poll():
        if flag.exists() or not alive(ppid) or time.time() - t0 > 90:
            try:
                flag.unlink()
            except OSError:
                pass
            root.destroy()
        else:
            root.after(150, poll)

    poll()
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
