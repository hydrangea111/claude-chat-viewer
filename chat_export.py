"""Claude Code 대화 뷰어: pywebview 창에 ui.html을 띄우고 core의 파싱 결과를 JS에 넘긴다."""
import json
import os
import re
import subprocess
import sys
import shutil
import tempfile
import threading
import time
import uuid
import webbrowser
from pathlib import Path

import webview

import core
import export

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
CATS = ("files", "cmds", "others")
TITLE = "Claude Code 대화 뷰어 v3.9"
ICON = BASE / "app.ico"


# 뷰어 입력창의 권한 단계. -p(화면 없는) 모드는 승인 질문을 못 하므로, 허용할 도구를 미리 정한다.
MODE_ARGS = {
    "read": ["--permission-mode", "default", "--allowedTools", "Read,Grep,Glob"],
    "edit": ["--permission-mode", "acceptEdits", "--allowedTools", "Read,Grep,Glob,Edit,Write,MultiEdit,NotebookEdit"],
    "all": ["--dangerously-skip-permissions"],
}
SETTINGS = Path(os.environ.get("APPDATA") or Path.home()) / "ClaudeChatViewer" / "settings.json"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: 검은 콘솔 창이 깜빡이지 않게


def find_claude():
    """claude 실행 파일 위치. PATH에 없어도 흔한 설치 위치를 확인한다(방금 설치해서 PATH가 아직 반영 안 된 경우 등)."""
    p = shutil.which("claude")
    if p:
        return p
    env = os.environ
    cands = [
        Path.home() / ".local" / "bin" / "claude.exe",
        Path.home() / ".claude" / "local" / "claude.exe",
        Path(env.get("LOCALAPPDATA", "")) / "Programs" / "claude" / "claude.exe",
        Path(env.get("APPDATA", "")) / "npm" / "claude.cmd",
        Path(env.get("ProgramFiles", "")) / "nodejs" / "claude.cmd",
    ]
    return next((str(c) for c in cands if c.is_file()), None)


def recycle(path):
    """파일을 영구 삭제하지 않고 휴지통으로 보낸다. 실패하면 False(절대 영구 삭제로 대체하지 않는다)."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    class OP(ctypes.Structure):
        _pack_ = 1 if ctypes.sizeof(ctypes.c_void_p) == 4 else 0  # SHFILEOPSTRUCTW는 32비트에서만 1바이트 정렬
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("aborted", wintypes.BOOL),
                    ("mappings", ctypes.c_void_p), ("title", wintypes.LPCWSTR)]

    op = OP()
    op.wFunc = 3                       # FO_DELETE
    op.pFrom = os.path.normpath(path) + "\0"   # 문자열 끝 이중 널
    op.fFlags = 0x40 | 0x10 | 0x4 | 0x400   # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.aborted and not os.path.exists(path)


WEBVIEW2_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"


def webview2_installed():
    """Microsoft Edge WebView2 런타임이 있는지(Windows 11은 기본 포함, 오래된 Windows 10은 없을 수 있다)."""
    if sys.platform != "win32":
        return True
    import winreg
    guid = r"Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for root, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node" + guid[8:]), (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE" + guid[8:]),
                      (winreg.HKEY_CURRENT_USER, guid)):
        try:
            with winreg.OpenKey(root, sub) as k:
                v = winreg.QueryValueEx(k, "pv")[0]
                if v and v != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def message_box(text, flags=0x40):
    if sys.platform == "win32":
        import ctypes
        return ctypes.windll.user32.MessageBoxW(None, text, "Claude Code 대화 뷰어", flags | 0x10000)  # MB_SETFOREGROUND
    print(text)
    return 0


def single_instance():
    """이미 실행 중이면 그 창을 앞으로 가져오고 True를 돌려준다.
    느린 PC에서 여러 번 눌러도 창이 쌓이지 않게 한다. 시험용으로 CCV_ALLOW_MULTIPLE=1이면 건너뛴다."""
    if sys.platform != "win32" or os.environ.get("CCV_ALLOW_MULTIPLE"):
        return False
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, r"Local\dh.claude-chat-viewer.single")
    if ctypes.windll.kernel32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS가 아니면 내가 첫 실행
        return False
    u = ctypes.windll.user32
    hwnd = u.FindWindowW(None, TITLE)
    if hwnd:
        u.ShowWindow(hwnd, 9)  # SW_RESTORE: 최소화돼 있으면 복원
        u.SetForegroundWindow(hwnd)
    return True


def set_window_icon():
    """pythonw.exe의 기본 아이콘 대신 app.ico를 창 제목줄과 작업표시줄에 쓴다."""
    if sys.platform != "win32" or not ICON.exists():
        return
    import ctypes
    u = ctypes.windll.user32
    hwnd = 0
    for _ in range(50):  # 창이 뜰 때까지 잠깐 기다린다
        hwnd = u.FindWindowW(None, TITLE)
        if hwnd:
            break
        time.sleep(0.1)
    if not hwnd:
        return
    for size, kind in ((16, 0), (32, 1)):  # ICON_SMALL, ICON_BIG
        h = u.LoadImageW(None, str(ICON), 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
        u.SendMessageW(hwnd, 0x80, kind, h)  # WM_SETICON


def clipboard_get():
    """클립보드의 글자를 읽는다. 웹뷰의 clipboard API는 권한 창이 뜨거나 막히는 PC가 있어 윈도우 API를 직접 쓴다."""
    if os.name != "nt":
        return ""
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    u.OpenClipboard.argtypes = [wintypes.HWND]
    u.GetClipboardData.argtypes = [wintypes.UINT]
    u.GetClipboardData.restype = wintypes.HANDLE
    k.GlobalLock.argtypes = [wintypes.HANDLE]
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalUnlock.argtypes = [wintypes.HANDLE]
    for _ in range(20):                      # 다른 프로그램이 잠깐 잡고 있을 수 있어 잠시 재시도
        if u.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        return ""
    try:
        h = u.GetClipboardData(13)           # CF_UNICODETEXT
        if not h:
            return ""
        p = k.GlobalLock(h)
        if not p:
            return ""
        try:
            return ctypes.wstring_at(p)
        finally:
            k.GlobalUnlock(h)
    finally:
        u.CloseClipboard()


def clipboard_set(text):
    """클립보드에 글자를 넣는다. 성공하면 True."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    u.OpenClipboard.argtypes = [wintypes.HWND]
    u.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    u.SetClipboardData.restype = wintypes.HANDLE
    k.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k.GlobalAlloc.restype = wintypes.HANDLE
    k.GlobalLock.argtypes = [wintypes.HANDLE]
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalUnlock.argtypes = [wintypes.HANDLE]
    k.GlobalFree.argtypes = [wintypes.HANDLE]
    data = (str(text) + "\0").encode("utf-16-le")
    h = k.GlobalAlloc(0x0002, len(data))     # GMEM_MOVEABLE
    if not h:
        return False
    p = k.GlobalLock(h)
    if not p:
        k.GlobalFree(h)
        return False
    ctypes.memmove(p, data, len(data))
    k.GlobalUnlock(h)
    for _ in range(20):
        if u.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        k.GlobalFree(h)
        return False
    try:
        u.EmptyClipboard()
        if not u.SetClipboardData(13, h):
            k.GlobalFree(h)
            return False
        return True                          # 성공하면 클립보드가 메모리를 소유한다
    finally:
        u.CloseClipboard()


SDK_MARK = re.compile(rb'"entrypoint"\s*:\s*"sdk-cli"')


def unmark_sdk(path):
    """뷰어(claude -p)가 쓴 대화 파일의 entrypoint 표시를 sdk-cli -> cli 로 바꿔, 터미널 Claude Code의 /resume 목록에도 보이게 한다.
    Claude Code는 파일 앞부분의 entrypoint가 sdk-*이면 SDK 대화로 보고 목록에서 뺀다.
    안전장치: 읽은 뒤 파일이 바뀌었으면 건드리지 않고, 바뀐 줄이 모두 올바른 JSON일 때만 임시 파일을 거쳐 통째로 교체한다. 바꿨으면 True."""
    try:
        st = os.stat(path)
        raw = Path(path).read_bytes()
        if not SDK_MARK.search(raw):
            return False
        lines = raw.split(b"\n")
        for i, ln in enumerate(lines):
            if SDK_MARK.search(ln):
                new = SDK_MARK.sub(b'"entrypoint":"cli"', ln)
                json.loads(new.decode("utf-8"))           # 깨진 줄이 생기면 예외 -> 아무것도 바꾸지 않는다
                lines[i] = new
        tmp = str(path) + ".ccv-tmp"
        Path(tmp).write_bytes(b"\n".join(lines))
        now = os.stat(path)
        if (now.st_mtime_ns, now.st_size) != (st.st_mtime_ns, st.st_size):   # 그 사이 다른 곳에서 썼다면 포기
            os.remove(tmp)
            return False
        os.replace(tmp, path)
        return True
    except (OSError, ValueError):
        try:
            os.remove(str(path) + ".ccv-tmp")
        except OSError:
            pass
        return False


def read_settings():
    try:
        d = json.loads(SETTINGS.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def custom_titles():
    t = read_settings().get("titles")
    return t if isinstance(t, dict) else {}


def session_info(path):
    """(제목, 시각). 뷰어에서 바꾼 이름이 있으면 그것을 우선한다."""
    title, ts = core.session_info(path)
    return custom_titles().get(Path(path).stem) or title, ts


class Api:
    def __init__(self):
        self._window = None
        self._cur = None
        self._cur_path = None
        self._title = ""
        self._run = None
        self._new_cwd = None
        self._initial = sys.argv[1] if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]) else None

    def get_initial(self):
        if not self._initial:
            return None
        title, ts = session_info(Path(self._initial))
        return {"path": self._initial, "title": title, "date": core.local_time(ts)}

    def list_sessions(self):
        files = sorted(core.PROJECTS.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True) \
            if core.PROJECTS.exists() else []
        out = []
        titles = custom_titles()
        for p in files:
            title, ts = core.session_info(p)
            title = titles.get(p.stem) or title
            out.append({"path": str(p), "title": title, "date": core.local_time(ts), "project": p.parent.name})
        return out

    def open_session(self, path, title, with_rem):
        self._cur_path, self._title = path, title
        self._cur = core.parse(Path(path), with_rem)
        where = {t["id"]: (cat, i) for cat in CATS for i, t in enumerate(self._cur[cat])}
        msgs = []
        for role, ts, parts in self._cur["msgs"]:
            ps = []
            for k, x in parts:
                if k == "tool":
                    cat, idx = where[x["id"]]
                    ps.append({"k": "tool", "cat": cat, "idx": idx, "name": x["name"], "sum": core.tool_summary(x),
                               "err": x["error"]})
                else:
                    ps.append({"k": k, "t": x})
            msgs.append({"role": role, "ts": ts, "parts": ps})
        d = self._cur
        return {
            "msgs": msgs,
            "ver": self._ver(path),
            "cwd": self._cwd_of(path),
            "files": [{"ts": t["ts"], "act": core.FILE_TOOLS[t["name"]], "path": core.file_path_of(t),
                       "exists": os.path.exists(core.file_path_of(t))} for t in d["files"]],
            "cmds": [{"ts": t["ts"], "tool": t["name"], "cmd": (t["input"].get("command") or "").strip().split("\n")[0][:300],
                      "state": "err" if t["error"] else ("none" if t["result"] is None else "ok")} for t in d["cmds"]],
            "others": [{"ts": t["ts"], "tool": t["name"], "sum": core.tool_summary(t)} for t in d["others"]],
        }

    def detail(self, cat, idx):
        t = self._cur[cat][idx]
        return {"text": core.clip(core.tool_detail(t)), "diff": t["name"] in ("Edit", "MultiEdit")}

    def _export(self, fmt):
        sid = Path(self._cur_path).stem
        return (export.to_html if fmt == "html" else export.to_txt)(self._cur, self._title, sid)

    def save(self, fmt):
        if not self._cur:
            return None
        safe = re.sub(r'[\\/:*?"<>|]', "_", self._title).strip(" .")[:50] or "chat"
        types = {"html": "HTML 문서 (*.html)", "txt": "텍스트 문서 (*.txt)"}
        dlg = getattr(webview, "FileDialog", None)
        mode = dlg.SAVE if dlg else webview.SAVE_DIALOG
        dest = self._window.create_file_dialog(mode, save_filename=f"{safe}.{fmt}", file_types=(types[fmt],))
        if not dest:
            return None
        dest = dest if isinstance(dest, str) else dest[0]
        if not dest.lower().endswith(f".{fmt}"):
            dest += f".{fmt}"
        # TXT는 UTF-8 BOM + CRLF: 메모장에서 한글이 깨지지 않는다
        with open(dest, "w", encoding="utf-8-sig" if fmt == "txt" else "utf-8",
                  newline="\r\n" if fmt == "txt" else None) as f:
            f.write(self._export(fmt))
        return dest

    def view_browser(self):
        if self._cur:
            tmp = Path(tempfile.gettempdir()) / f"claude_chat_{Path(self._cur_path).stem}.html"
            tmp.write_text(self._export("html"), encoding="utf-8")
            webbrowser.open(tmp.as_uri())

    def pick_files(self):
        """입력창에 경로를 넣을 파일을 고른다(여러 개 가능). 대화 파일이 아니라 Claude에게 읽힐 파일이다."""
        dlg = getattr(webview, "FileDialog", None)
        mode = dlg.OPEN if dlg else webview.OPEN_DIALOG
        r = self._window.create_file_dialog(mode, allow_multiple=True, directory=str(Path.home()))
        return [str(x) for x in r] if r else []

    # ---- 입력창: 설치된 Claude Code(claude -p)로 이어서 말하기 ----
    def claude_available(self):
        return bool(find_claude())

    def new_chat(self):
        self._cur, self._cur_path, self._title, self._new_cwd = None, None, "", None

    def pick_folder(self):
        """새 대화에서 Claude가 작업할 폴더를 고르게 한다."""
        dlg = getattr(webview, "FileDialog", None)
        mode = dlg.FOLDER if dlg else webview.FOLDER_DIALOG
        r = self._window.create_file_dialog(mode, directory=str(Path.home()))
        if not r:
            return None
        self._new_cwd = r if isinstance(r, str) else r[0]
        return self._new_cwd

    def get_clipboard(self):
        return clipboard_get()

    def set_clipboard(self, text):
        return clipboard_set(text)

    def get_setting(self, key):
        return read_settings().get(key)

    def set_setting(self, key, val):
        try:
            d = read_settings()
            d[key] = val
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            return True
        except OSError:
            return False

    def rename_session(self, path, title):
        """대화 이름을 바꾼다. 대화 파일은 그대로 두고 뷰어 설정에만 저장한다(빈 이름이면 원래 이름으로 되돌림)."""
        try:
            p = Path(path).resolve()
            if p.suffix != ".jsonl" or core.PROJECTS.resolve() not in p.parents:
                return {"ok": False, "error": "Claude Code 대화 폴더 밖의 파일은 바꿀 수 없어요"}
            title = " ".join(str(title or "").split())[:80]
            d = read_settings()
            titles = custom_titles()
            if title:
                titles[p.stem] = title
            else:
                titles.pop(p.stem, None)
            d["titles"] = titles
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            return {"ok": True, "title": title or core.session_info(p)[0]}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def delete_session(self, path):
        """대화 파일을 휴지통으로 옮긴다. Claude Code가 저장하는 폴더 안의 .jsonl만 대상이다."""
        try:
            p = Path(path).resolve()
            if p.suffix != ".jsonl" or core.PROJECTS.resolve() not in p.parents:
                return {"ok": False, "error": "Claude Code 대화 폴더 밖의 파일은 삭제하지 않습니다"}
            if self._run and self._run["proc"].poll() is None and self._run.get("path") == str(p):
                return {"ok": False, "error": "응답 중인 대화는 삭제할 수 없어요"}
            if not recycle(str(p)):
                return {"ok": False, "error": "휴지통으로 옮기지 못했습니다(파일이 사용 중일 수 있어요)"}
            if self._cur_path and Path(self._cur_path).resolve() == p:
                self._cur = self._cur_path = None
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _cwd_of(path):
        for r in core.read_lines(Path(path)):
            c = r.get("cwd")
            if c and os.path.isdir(c):
                return c
        return None

    @staticmethod
    def _ver(path):
        try:
            st = os.stat(path)
            return [st.st_mtime_ns, st.st_size]
        except OSError:
            return None

    def session_state(self, path):
        """세션 파일의 마지막 수정 후 경과 초와 버전. 뷰어가 마지막으로 본 버전과 다르고 방금 바뀌었다면 다른 곳에서 쓰는 중일 수 있다."""
        v = self._ver(path)
        return {"ver": v, "idle": (time.time() - v[0] / 1e9) if v else None}

    def send(self, text, mode, files=None):
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "빈 메시지입니다"}
        if self._run and self._run["proc"].poll() is None:
            return {"ok": False, "error": "이미 응답을 기다리는 중입니다"}
        exe = find_claude()
        if not exe:
            return {"ok": False, "error": "claude 명령을 찾을 수 없습니다. Claude Code를 설치하고 로그인해 주세요"}
        args = [exe, "-p", "--output-format", "stream-json", "--verbose", *MODE_ARGS.get(mode, MODE_ARGS["read"])]
        # 입력창에 넣은 파일이 작업 폴더 밖에 있어도 읽을 수 있게, 그 파일이 있는 폴더만 추가로 허용한다
        dirs = {os.path.dirname(f) for f in files or [] if isinstance(f, str) and os.path.isfile(f)}
        for d in sorted(dirs):
            args += ["--add-dir", d]
        path = self._cur_path
        if path:
            sid = Path(path).stem
            cwd = self._cwd_of(path) or str(Path.home())  # 세션은 만든 폴더 기준으로 저장되므로 그 폴더에서 이어 간다
            args += ["--resume", sid]
        else:
            sid = str(uuid.uuid4())
            cwd = self._new_cwd if self._new_cwd and os.path.isdir(self._new_cwd) else str(Path.home())
            args += ["--session-id", sid]
        try:
            proc = subprocess.Popen(args, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        except OSError as e:
            return {"ok": False, "error": f"실행하지 못했습니다: {e}"}
        run = {"proc": proc, "sid": sid, "path": path, "result": None, "stderr": ""}
        self._run = run

        def feed():
            try:
                proc.stdin.write(text.encode("utf-8"))  # 인자가 아니라 표준입력으로 넘겨 따옴표·길이 문제를 피한다
                proc.stdin.close()
            except OSError:
                pass

        def read_out():
            for line in proc.stdout:
                try:
                    ev = json.loads(line.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if ev.get("type") == "result":
                    run["result"] = ev

        def read_err():
            run["stderr"] = proc.stderr.read().decode("utf-8", "replace")

        for fn in (feed, read_out, read_err):
            threading.Thread(target=fn, daemon=True).start()
        return {"ok": True}

    def poll(self):
        r = self._run
        if not r:
            return {"running": False}
        if not r["path"]:
            hit = next(core.PROJECTS.glob(f"*/{r['sid']}.jsonl"), None) if core.PROJECTS.exists() else None
            r["path"] = str(hit) if hit else None
        running = r["proc"].poll() is None
        if not running and r["path"] and not r.get("unmarked"):
            r["unmarked"] = True
            if read_settings().get("terminal_visible", True):
                unmark_sdk(r["path"])
        ver = None
        if r["path"]:
            try:
                st = os.stat(r["path"])
                ver = [st.st_mtime_ns, st.st_size]
            except OSError:
                pass
        error = None
        if not running:
            res = r["result"] or {}
            if res.get("is_error"):
                error = str(res.get("result") or "오류가 났습니다")
            elif r["proc"].returncode:
                error = (r["stderr"].strip().splitlines() or [f"종료 코드 {r['proc'].returncode}"])[-1]
        return {"running": running, "path": r["path"], "ver": ver, "error": error}

    def stop(self):
        r = self._run
        if r and r["proc"].poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(r["proc"].pid), "/T", "/F"], creationflags=NO_WINDOW,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                r["proc"].terminate()

    def open_path(self, idx, folder):
        p = core.file_path_of(self._cur["files"][idx])
        if not os.path.exists(p):
            return False
        if folder:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(p)])
        else:
            os.startfile(p)
        return True


if __name__ == "__main__":
    if single_instance():
        sys.exit(0)
    if sys.platform == "win32":  # 작업표시줄에서 pythonw와 묶이지 않고 이 프로그램의 아이콘으로 보이게
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("dh.claude-chat-viewer")
    if not webview2_installed():  # 없으면 창이 빈 화면이거나 아예 안 뜨므로 먼저 알린다
        if message_box("화면을 그리는 Microsoft Edge WebView2 런타임을 찾지 못했어요.\n설치 페이지를 열까요?\n(아니오를 누르면 그대로 실행을 시도합니다)", 0x24) == 6:  # MB_YESNO|ICONQUESTION, IDYES
            webbrowser.open(WEBVIEW2_URL)
            sys.exit(0)
    api = Api()
    api._window = webview.create_window(TITLE, (BASE / "ui.html").as_uri(), js_api=api,
                                       width=1280, height=800, min_size=(900, 560), background_color="#0f1115")
    api._window.events.closed += api.stop  # 창을 닫으면 응답 중이던 claude도 같이 끝낸다
    threading.Thread(target=set_window_icon, daemon=True).start()
    try:  # 파일을 창에 끌어다 놓으면 주소창에 입력되고 열린다(pywebview 5 이상)
        from webview.dom import DOMEventHandler

        def on_drop(e):
            files = (e.get("dataTransfer") or {}).get("files") or []
            paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
            if paths:
                api._window.evaluate_js("dropOpen(%s)" % json.dumps(paths))

        api._window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
    except Exception:
        pass
    try:
        webview.start()
    except Exception as e:  # 창을 못 띄우면 조용히 사라지지 않고 이유를 알린다
        message_box("창을 열지 못했어요.\n\n" + str(e)[:400], 0x10)
        raise
