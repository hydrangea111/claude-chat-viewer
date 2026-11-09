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
    w, h = pic.width(), pic.height()
    cv = tk.Canvas(root, width=w, height=h, highlightthickness=0, borderwidth=0)
    cv.pack()
    cv.create_image(0, 0, image=pic, anchor="nw")
    cv.create_oval(624, 74, 664, 114, outline="#e6ded1", width=5)
    arc = cv.create_arc(624, 74, 664, 114, style="arc", start=90, extent=110, outline="#c8643c", width=5)
    bar = cv.create_rectangle(-150, 190, 0, 195, fill="#c8643c", outline="")
    st = {"a": 90, "x": -150}

    def spin():   # 멈춘 게 아니라는 표시
        st["a"] -= 12
        st["x"] = st["x"] + 10 if st["x"] < 700 else -150
        cv.itemconfigure(arc, start=st["a"])
        cv.coords(bar, st["x"], 190, st["x"] + 150, 195)
        root.after(30, spin)
    root.update_idletasks()
    root.geometry("%dx%d+%d+%d" % (w, h, (root.winfo_screenwidth() - w) // 2, (root.winfo_screenheight() - h) // 2))
    drag = {}
    lab = cv
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

    spin()
    poll()
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
