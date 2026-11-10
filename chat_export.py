"""Claude Code 대화창: pywebview 창에 ui.html을 띄우고 core의 파싱 결과를 JS에 넘긴다."""
import base64
import json
import zipfile
import xml.etree.ElementTree as ET
import os
import re
import subprocess
import sys
import shutil
import socket
import tempfile
import urllib.request
import threading
import time
import uuid
import platform
import webbrowser
from pathlib import Path

SRC_SPLASH_FLAG = Path(tempfile.gettempdir()) / ("ccv_splash_%d.flag" % os.getpid())
if sys.platform == "win32" and not getattr(sys, "frozen", False) and (Path(__file__).parent / "src_splash.py").exists():
    # 소스로 실행할 때: 무거운 불러오기(webview 등)보다 먼저 '여는 중입니다' 안내 창을 따로 띄운다
    try:
        subprocess.Popen([sys.executable, str(Path(__file__).parent / "src_splash.py"), str(SRC_SPLASH_FLAG), str(os.getpid())],
                         creationflags=0x08000000, close_fds=True)  # CREATE_NO_WINDOW
    except Exception:
        pass

import webview

import core
import export
import voice

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
CATS = ("files", "cmds", "others")
TITLE = "Claude Code 대화창 v6.2"
APP_VERSION = re.search(r"v(\d+(?:\.\d+)*)", TITLE).group(1)
SITE_URL = "https://dh-chat-viewer.web.app/"
UPDATE_URL = os.environ.get("CCV_UPDATE_URL") or SITE_URL + "version.json"   # 새 버전 확인용 작은 파일(글자 몇 줄)


# 개발자에게 문의하기: 개발자의 Firebase(Firestore)에 글 한 건을 남긴다. 규칙상 새 글 작성만 되고, 읽기·수정·삭제는 개발자만 가능하다.
INQUIRY_URL = "https://firestore.googleapis.com/v1/projects/dh-link-hub/databases/(default)/documents/viewerInquiries"
INQUIRY_KEY = "AIzaSyDVKxVqqmvO4eZa00sLaAxzMvkfqfBlWn4"   # 웹용 공개 키(비밀이 아님). 접근 제어는 Firestore 규칙이 한다


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:4])


def close_splash():
    """exe 로 열 때 먼저 뜨는 '여는 중' 안내 창을 닫는다(소스로 실행하면 해당 없음)."""
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass
    try:  # 소스 실행용 안내 창에 닫으라는 신호를 보낸다
        if SRC_SPLASH_FLAG.parent.exists():
            SRC_SPLASH_FLAG.write_text("x")
    except Exception:
        pass
ICON = BASE / "app.ico"


# 대화창 입력창의 권한 단계. -p(화면 없는) 모드는 승인 질문을 못 하므로, 허용할 도구를 미리 정한다.
MODE_ARGS = {
    "read": ["--permission-mode", "default", "--allowedTools", "Read,Grep,Glob"],
    "edit": ["--permission-mode", "acceptEdits", "--allowedTools", "Read,Grep,Glob,Edit,Write,MultiEdit,NotebookEdit"],
    "all": ["--dangerously-skip-permissions"],
}
# 모델 선택 버튼. 이름은 --model 에 그대로 넘긴다(비어 있으면 Claude Code 기본 설정을 따른다)
MODELS = [
    {"id": "", "label": "기본", "desc": "Claude Code 설정을 따릅니다"},
    {"id": "claude-fable-5-1", "label": "Fable 5.1", "desc": "가장 똑똑한 모델"},
    {"id": "claude-opus-5-5", "label": "Opus 5.5", "desc": "어려운 일에"},
    {"id": "claude-sonnet-5-5", "label": "Sonnet 5.5", "desc": "빠르고 균형 잡힌 모델"},
    {"id": "claude-haiku-5-5", "label": "Haiku 5.5", "desc": "가장 빠르고 가볍습니다"},
]
MODEL_IDS = {m["id"] for m in MODELS}
# 생각 깊이(--effort). 높을수록 신중하지만 느리고 사용량이 많다
EFFORTS = [
    {"id": "", "label": "기본", "desc": "Claude Code 설정을 따릅니다"},
    {"id": "low", "label": "낮음", "desc": "빠르고 가볍게"},
    {"id": "medium", "label": "보통", "desc": "무난하게"},
    {"id": "high", "label": "높음", "desc": "신중하게"},
    {"id": "xhigh", "label": "매우 높음", "desc": "아주 깊게 (느리고 사용량 많음)"},
    {"id": "max", "label": "최대", "desc": "끝까지 (가장 느리고 사용량 가장 많음)"},
]
EFFORT_IDS = {e["id"] for e in EFFORTS}

# -p 모드에는 선택창(AskUserQuestion)이 없다. 대신 이 형식의 블록을 답 끝에 붙이게 해서 대화창이 버튼으로 바꿔 그린다.
CHOICES_PROMPT = (
    "이 대화는 Claude Code 대화창에서 진행 중이며 AskUserQuestion 도구는 쓸 수 없다. "
    "사용자에게 여러 선택지 중 하나를 고르게 해야 하면, 답변 맨 끝에 아래 형식의 코드 블록을 정확히 한 개만 붙여라. "
    "블록 밖에는 질문 내용을 평소처럼 설명하고, 선택지는 2~6개의 짧은 문장으로 써라.\n"
    "```choices\n{\"question\": \"질문\", \"options\": [\"선택지1\", \"선택지2\"]}\n```\n"
    "자유롭게 답해도 되는 질문에는 이 블록을 쓰지 마라."
)
def prompt_file_args():
    """선택 버튼 안내문을 파일로 저장해 그 경로만 넘긴다. 줄바꿈·따옴표·한글이 든 긴 글을 명령줄로 직접 넘기면
    claude 가 .cmd 로 설치된 PC에서 깨지거나 잘리기 때문이다. 파일을 못 쓰면 안내문 없이 보낸다(버튼만 빠진다)."""
    f = SETTINGS.parent / "choices_prompt.txt"
    try:
        if not f.is_file() or f.read_text(encoding="utf-8") != CHOICES_PROMPT:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(CHOICES_PROMPT, encoding="utf-8")
        return ["--append-system-prompt-file", str(f)]
    except OSError:
        return []


# 대화창 입력창에서 쓸 수 없는 터미널 전용 단축어(-p 에서는 동작하지 않는 내장 명령)
BUILTIN_SLASH = {
    "advisor", "agents", "auto-mode-setup", "autocompact", "clear", "color", "compact", "config", "output-style",
    "context", "effort", "fast", "focus", "heapdump", "init", "mcp", "import", "model", "__remote-workflow",
    "workflow-launch-exec", "reload-plugins", "reload-skills", "rename", "ultrareview", "usage-credits",
    "extra-usage", "usage", "insights", "recap", "skill-doctor", "goal", "design-consent", "design-revoke",
    "list-agents", "team-onboarding", "doctor", "send-to-project", "login", "logout", "help", "exit", "resume",
}

_AUTH_PAT = re.compile(r"invalid api key|/login|please run.*login|authentication[_ ]error|oauth token.*(expired|revoked)|"
                       r"not logged in|unauthorized|\b401\b|credentials|token has expired", re.I)
_NET_PAT = re.compile(r"econnrefused|enotfound|etimedout|econnreset|eai_again|fetch failed|unable to connect|"
                      r"network (error|is unreachable)|getaddrinfo|socket hang up|connection (error|refused|reset|timed out)|"
                      r"timed? ?out|offline", re.I)


def classify_error(text, status=None):
    """오류 문구/HTTP 상태를 사용자가 이해할 갈래로 나눈다: auth(로그인) | net(연결) | limit(사용량) | busy(서버 혼잡) | other"""
    t = str(text or "")
    try:
        st = int(status) if status is not None else None
    except (TypeError, ValueError):
        st = None
    if st in (401, 403) or _AUTH_PAT.search(t):
        return "auth"
    if st == 429 or re.search(r"rate.?limit|usage limit|limit reached|too many requests|quota", t, re.I):
        return "limit"
    if st in (500, 502, 503, 504, 529) or re.search(r"overloaded|server error|internal error|\b529\b", t, re.I):
        return "busy"
    if _NET_PAT.search(t):
        return "net"
    return "other"


def parse_auth_status(text):
    """`claude auth status` 의 JSON 출력 -> True(로그인됨) / False(로그아웃) / None(알 수 없음)"""
    try:
        v = json.loads(text).get("loggedIn")
        return v if isinstance(v, bool) else None
    except (ValueError, AttributeError):
        return None


def net_ok(host="api.anthropic.com", port=443, timeout=3.0):
    """Anthropic 서버에 인터넷으로 닿는지(로그인과 상관없이 연결만 확인)"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def scan_user_commands():
    """사용자가 직접 만든 단축어(~/.claude/commands, ~/.claude/skills)를 파일에서 읽는다. 아직 한 번도 대화한 적 없어도 목록이 나오게 하는 용도."""
    out = []
    base = Path.home() / ".claude"
    try:
        for f in sorted((base / "commands").rglob("*.md")):
            out.append(f.relative_to(base / "commands").with_suffix("").as_posix().replace("/", ":"))
        for f in sorted((base / "skills").glob("*/SKILL.md")):
            out.append(f.parent.name)
    except OSError:
        pass
    return out


def scan_plugin_commands(limit=400):
    """설치된 플러그인의 단축어(이름은 `플러그인:명령`)를 파일에서 읽는다. 첫 대화 전에도 목록이 나오게 하는 용도이고,
    대화를 한 번 하면 claude 가 알려 준 정확한 목록이 대신 쓰인다. 오래 걸리지 않게 깊이와 개수를 제한한다."""
    out = []
    root = Path.home() / ".claude" / "plugins"
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).relative_to(root).parts)
            dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git", "__pycache__")] if depth < 7 else []
            if Path(dirpath).name != ".claude-plugin" or "plugin.json" not in filenames:
                continue
            plug = Path(dirpath).parent
            try:
                name = json.loads((Path(dirpath) / "plugin.json").read_text(encoding="utf-8")).get("name") or plug.name
            except (OSError, ValueError):
                name = plug.name
            for f in sorted((plug / "commands").glob("*.md")):
                out.append(f"{name}:{f.stem}")
            for f in sorted((plug / "skills").glob("*/SKILL.md")):
                out.append(f"{name}:{f.parent.name}")
            if len(out) >= limit:
                break
    except OSError:
        pass
    return out


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
        return ctypes.windll.user32.MessageBoxW(None, text, "Claude Code 대화창", flags | 0x10000)  # MB_SETFOREGROUND
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
    from ctypes import wintypes
    me = os.getpid()
    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def find():  # 같은 제목의 다른 창이 아니라 이 프로그램 자신의 창만 찾는다
        found = []

        def cb(hw, lp):
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hw, ctypes.byref(pid))
            if pid.value == me and u.IsWindowVisible(hw):
                n = u.GetWindowTextLengthW(hw)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    u.GetWindowTextW(hw, buf, n + 1)
                    if buf.value == TITLE:
                        found.append(hw)
            return True
        u.EnumWindows(CB(cb), 0)
        return found[0] if found else 0

    def apply(hwnd):
        for metric, kind in ((49, 0), (11, 1)):  # SM_CXSMICON/ICON_SMALL, SM_CXICON/ICON_BIG
            size = u.GetSystemMetrics(metric) or 32
            h = u.LoadImageW(None, str(ICON), 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
            if h:
                u.SendMessageW(hwnd, 0x80, kind, h)  # WM_SETICON
    t0 = time.time()
    while time.time() - t0 < 120:  # 시작이 느린 PC에서는 창이 한참 뒤에 뜨므로 넉넉히 기다린다
        hwnd = find()
        if hwnd:
            break
        time.sleep(0.2)
    else:
        return
    for wait in (0, 1.5, 4, 10):  # 웹뷰가 아이콘을 다시 덮어쓰는 경우를 대비해 몇 번 더 적용한다
        time.sleep(wait)
        hwnd = find() or hwnd
        apply(hwnd)


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
    """대화창(claude -p)가 쓴 대화 파일의 entrypoint 표시를 sdk-cli -> cli 로 바꿔, 터미널 Claude Code의 /resume 목록에도 보이게 한다.
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


def save_setting(key, val):
    try:
        d = read_settings()
        d[key] = val
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return True
    except OSError:
        return False


def session_usage(path):
    """대화 파일에 기록된 토큰 사용량 합계. 한 응답이 블록마다 여러 줄로 기록되므로 message.id 로 중복을 뺀다."""
    seen = {}
    try:
        for r in core.read_lines(Path(path)):
            m = r.get("message")
            if r.get("type") == "assistant" and isinstance(m, dict) and isinstance(m.get("usage"), dict):
                seen[m.get("id") or id(r)] = m["usage"]
    except OSError:
        return None
    tot = {"in": 0, "out": 0, "cache_read": 0, "cache_new": 0, "turns": len(seen)}
    for u in seen.values():
        tot["in"] += int(u.get("input_tokens") or 0)
        tot["out"] += int(u.get("output_tokens") or 0)
        tot["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
        tot["cache_new"] += int(u.get("cache_creation_input_tokens") or 0)
    return tot


def custom_titles():
    t = read_settings().get("titles")
    return t if isinstance(t, dict) else {}


def session_info(path):
    """(제목, 시각). 대화창에서 바꾼 이름이 있으면 그것을 우선한다."""
    title, ts = core.session_info(path)
    return custom_titles().get(Path(path).stem) or title, ts


OFFICE_KINDS = {".docx": "Word 문서", ".pptx": "파워포인트", ".xlsx": "엑셀", ".hwpx": "한글(hwpx)"}
OLD_OFFICE = {".doc", ".ppt", ".xls", ".hwp"}


def _ln(el):
    return el.tag.rsplit("}", 1)[-1]


def _xml(z, name):
    zi = z.getinfo(name)
    if zi.file_size > 40 * 1024 * 1024:
        raise ValueError("안의 파일이 너무 큽니다")
    return ET.fromstring(z.read(name))


def _runs(el):
    """문단 하나의 글자: t 는 글자, tab/br 은 공백·줄바꿈."""
    out = []
    for x in el.iter():
        n = _ln(x)
        if n == "t":
            out.append(x.text or "")
        elif n == "tab":
            out.append("\t")
        elif n in ("br", "lineBreak"):
            out.append("\n")
    return "".join(out)


def _paras(root, para, cell="tc", row="tr", table="tbl"):
    """문서 순서대로 문단과 표(칸은 ' | ' 로 구분)를 줄로 만든다."""
    lines = []

    def walk(el):
        for ch in el:
            n = _ln(ch)
            if n == para:
                lines.append(_runs(ch))
            elif n == table:
                for r in ch.iter():
                    if _ln(r) == row:
                        lines.append(" | ".join(_runs(c).replace("\n", " ") for c in r if _ln(c) == cell))
                lines.append("")
            else:
                walk(ch)
    walk(root)
    return lines


def _col(ref):
    n = 0
    for c in ref:
        if not c.isalpha():
            break
        n = n * 26 + ord(c.upper()) - 64
    return max(n - 1, 0)


def _xlsx(z):
    names = z.namelist()
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in _xml(z, "xl/sharedStrings.xml"):
            shared.append(_runs(si))
    sheets = []
    if "xl/workbook.xml" in names and "xl/_rels/workbook.xml.rels" in names:
        rels = {r.get("Id"): r.get("Target") for r in _xml(z, "xl/_rels/workbook.xml.rels")}
        wb = _xml(z, "xl/workbook.xml")
        for sh in wb.iter():
            if _ln(sh) == "sheet":
                rid = [v for k, v in sh.attrib.items() if k.endswith("}id")]
                t = rels.get(rid[0]) if rid else None
                if t:
                    t = t.lstrip("/")
                    sheets.append((sh.get("name", ""), t if t.startswith("xl/") else "xl/" + t))
    if not sheets:
        sheets = [("시트", n) for n in sorted(names) if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
    lines = []
    for name, part in sheets:
        if part not in names:
            continue
        lines.append("══ 시트: " + name + " ══")
        rows = 0
        for row in _xml(z, part).iter():
            if _ln(row) != "row":
                continue
            cells = {}
            for c in row:
                if _ln(c) != "c":
                    continue
                v = ""
                kind = c.get("t")
                for ch in c:
                    if _ln(ch) == "v":
                        v = ch.text or ""
                    elif _ln(ch) == "is":
                        v = _runs(ch)
                if kind == "s" and v.isdigit() and int(v) < len(shared):
                    v = shared[int(v)]
                cells[_col(c.get("r", "A"))] = v.replace("\n", " ")
            if cells:
                lines.append("\t".join(cells.get(i, "") for i in range(max(cells) + 1)))
                rows += 1
                if rows >= 3000:
                    lines.append("(3000줄까지만 보여 줍니다)")
                    break
        lines.append("")
    return lines


def office_text(p, ext):
    """docx·pptx·xlsx·hwpx 에서 글자만 뽑는다. 서식과 그림은 빼고, 파일은 읽기만 한다."""
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        if ext == ".docx":
            return _paras(_xml(z, "word/document.xml"), "p")
        if ext == ".pptx":
            sl = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.findall(r"\d+", n)[-1]))
            out = []
            for i, n in enumerate(sl, 1):
                out.append("══ 슬라이드 %d ══" % i)
                out += [x for x in _paras(_xml(z, n), "p") if x.strip()]
                out.append("")
            return out
        if ext == ".xlsx":
            return _xlsx(z)
        sec = sorted(n for n in names if re.fullmatch(r"Contents/section\d+\.xml", n))
        out = []
        for n in sec:
            out += _paras(_xml(z, n), "p")
        return out


PV_LANGS = {'.py': 'Python', '.pyw': 'Python', '.c': 'C', '.h': 'C/C++ 헤더', '.cpp': 'C++', '.cc': 'C++', '.cxx': 'C++', '.hpp': 'C++ 헤더', '.cs': 'C#', '.java': 'Java', '.kt': 'Kotlin', '.js': 'JavaScript', '.mjs': 'JavaScript', '.ts': 'TypeScript', '.tsx': 'TSX', '.jsx': 'JSX', '.go': 'Go', '.rs': 'Rust', '.rb': 'Ruby', '.php': 'PHP', '.swift': 'Swift', '.lua': 'Lua', '.r': 'R', '.sql': 'SQL', '.sh': '셸', '.bat': '배치', '.cmd': '배치', '.ps1': 'PowerShell', '.json': 'JSON', '.yaml': 'YAML', '.yml': 'YAML', '.toml': 'TOML', '.ini': 'INI', '.xml': 'XML', '.css': 'CSS', '.csv': 'CSV', '.tsv': 'TSV', '.log': '로그', '.txt': '텍스트', '.ipynb': '노트북(JSON)', '.gradle': 'Gradle', '.cfg': '설정', '.env': '환경 설정'}


class Api:
    def __init__(self):
        self._edit_paths = {}
        self._term = None
        self._term_cwd = str(Path.home())
        self._term_hint = None
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

    def search_sessions(self, q):
        """대화 내용 검색: {경로: {"snip": 일치한 곳 앞뒤 글, "n": 일치 횟수}}. 파일이 바뀌지 않았으면 읽어 둔 글을 다시 쓴다."""
        q = (q or "").strip().lower()
        if len(q) < 2 or not core.PROJECTS.exists():
            return {}
        cache = self.__dict__.setdefault("_txt_cache", {})
        out = {}
        for p in core.PROJECTS.glob("*/*.jsonl"):
            try:
                st = p.stat()
            except OSError:
                continue
            key = (st.st_mtime_ns, st.st_size)
            ent = cache.get(str(p))
            if not ent or ent[0] != key:
                try:
                    txt = core.plain_text(p)
                except OSError:
                    continue
                ent = (key, txt, txt.lower())
                cache[str(p)] = ent
            low = ent[2]
            i = low.find(q)
            if i < 0:
                continue
            txt = ent[1]
            a, b = max(0, i - 28), min(len(txt), i + len(q) + 60)
            snip = " ".join(txt[a:b].replace("**", "").replace("`", "").split())
            out[str(p)] = {"snip": ("…" if a else "") + snip + ("…" if b < len(txt) else ""), "n": low.count(q)}
        return out

    def open_session(self, path, title, with_rem):
        self._cur_path, self._title = path, title
        self._cur = core.parse(Path(path), with_rem)
        where = {t["id"]: (cat, i) for cat in CATS for i, t in enumerate(self._cur[cat])}
        msgs = []
        for role, ts, parts in self._cur["msgs"]:
            ps = []
            for k, x in parts:
                if k == "tool" and x["name"] == "AskUserQuestion" and isinstance(x["input"].get("questions"), list):
                    qs = []
                    for q in x["input"]["questions"]:
                        if not isinstance(q, dict):
                            continue
                        opts = [{"label": str(o.get("label", "")), "desc": str(o.get("description", ""))}
                                for o in q.get("options", []) if isinstance(o, dict) and o.get("label")]
                        if q.get("question") and opts:
                            qs.append({"q": str(q["question"]), "h": str(q.get("header", "")), "opts": opts,
                                       "multi": bool(q.get("multiSelect"))})
                    if qs:
                        ps.append({"k": "ask", "qs": qs, "answered": x["result"] is not None and not x["error"]})
                        continue
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
            "usage": session_usage(path),
            "ver": self._ver(path),
            "cwd": self._cwd_of(path),
            "files": [{"ts": t["ts"], "act": core.FILE_TOOLS[t["name"]], "path": core.file_path_of(t),
                       "exists": os.path.exists(self._resolve(core.file_path_of(t)))} for t in d["files"]],
            "cmds": [{"ts": t["ts"], "tool": t["name"], "cmd": (t["input"].get("command") or "").strip().split("\n")[0][:300],
                      "state": "err" if t["error"] else ("none" if t["result"] is None else "ok")} for t in d["cmds"]],
            "others": [{"ts": t["ts"], "tool": t["name"], "sum": core.tool_summary(t)} for t in d["others"]],
        }

    def _resolve(self, p):
        """대화에 적힌 경로를 실제 경로로: ~, /c/Users/..(Git Bash), /mnt/c/..(WSL), 슬래시, 상대 경로(대화 폴더 기준)를 풀어 준다."""
        if not p:
            return ""
        p = os.path.expandvars(os.path.expanduser(str(p).strip().strip('"')))
        m = re.match(r"^/(?:mnt/)?([a-zA-Z])/(.*)$", p)
        if m and os.name == "nt":
            p = m.group(1).upper() + ":\\" + m.group(2)
        if os.name == "nt":
            p = p.replace("/", "\\")
        if not os.path.isabs(p):
            try:
                base = self._cwd_of(self._cur_path) or ""
            except Exception:
                base = ""
            p = os.path.join(base, p) if base else p
        return os.path.normpath(p)

    def _fp(self, idx):
        return self._resolve(core.file_path_of(self._cur["files"][idx]))

    def tool_copy(self, cat, idx):
        """대화 속 도구 칩 하나의 복사용 글: 명령은 전체 명령, 파일은 경로, 그 밖은 요약."""
        try:
            t = self._cur[cat][idx]
        except (TypeError, KeyError, IndexError):
            return ""
        i = t["input"]
        if t["name"] in core.CMD_TOOLS:
            return str(i.get("command") or "")
        if t["name"] in core.FILE_TOOLS:
            return core.file_path_of(t)
        return core.tool_summary(t)

    # ---------- 터미널(cmd 창처럼): 대화 폴더에서 명령을 바로 실행 ----------
    def term_cwd(self, hint=""):
        hint = hint or ""
        if getattr(self, "_term_hint", None) != hint:
            self._term_hint = hint
            self._term_cwd = hint if hint and os.path.isdir(hint) else str(Path.home())
        return self._term_cwd

    def term_run(self, cmd, hint=""):
        cwd = self.term_cwd(hint)
        cmd = (cmd or "").strip()
        if not cmd:
            return {"ok": False, "error": ""}
        if self._term and self._term["proc"].poll() is None:
            return {"ok": False, "error": "아직 실행 중인 명령이 있습니다 (Ctrl+C 로 멈춥니다)"}
        m = re.match(r"^cd(?:\s+/d)?(?:\s+(.*))?$", cmd, re.I)
        if m:   # cd 는 이 창 안에서만 폴더를 바꾼다
            arg = (m.group(1) or "").strip().strip('"')
            if not arg:
                return {"ok": True, "done": True, "text": cwd + "\n"}
            tgt = os.path.normpath(os.path.join(cwd, os.path.expanduser(arg)))
            if os.path.isdir(tgt):
                self._term_cwd = tgt
                return {"ok": True, "done": True, "text": ""}
            return {"ok": True, "done": True, "text": "지정된 경로를 찾을 수 없습니다.\n"}
        import codecs
        enc = "utf-8"
        if os.name == "nt":
            try:
                import ctypes
                enc = "cp%d" % ctypes.windll.kernel32.GetOEMCP()
            except Exception:
                enc = "cp949"
        try:
            proc = subprocess.Popen('cmd.exe /d /s /c "' + cmd + '"', cwd=cwd, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as e:
            return {"ok": False, "error": "실행하지 못했습니다 (" + str(e)[:80] + ")"}
        st = {"proc": proc, "text": "", "lock": threading.Lock()}
        self._term = st
        ansi = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

        def pump():
            dec = codecs.getincrementaldecoder(enc)(errors="replace")
            try:
                while True:
                    b = proc.stdout.read1(4096)
                    if not b:
                        break
                    t = ansi.sub("", dec.decode(b))
                    with st["lock"]:
                        if len(st["text"]) < 600_000:
                            st["text"] += t
                with st["lock"]:
                    st["text"] += ansi.sub("", dec.decode(b"", final=True))
            except (OSError, ValueError):
                pass
            proc.wait()
            with st["lock"]:
                st["eof"] = True
        threading.Thread(target=pump, daemon=True).start()
        return {"ok": True, "done": False}

    def term_poll(self, pos):
        st = self._term
        if not st:
            return {"text": "", "pos": 0, "done": True, "code": 0}
        with st["lock"]:
            text, n, done = st["text"][pos:], len(st["text"]), st.get("eof", False)
        return {"text": text, "pos": n, "done": done, "code": st["proc"].returncode if done else None}

    def term_stop(self):
        st = self._term
        if st and st["proc"].poll() is None:
            try:
                subprocess.run(["taskkill", "/PID", str(st["proc"].pid), "/T", "/F"], capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=10)
            except (OSError, subprocess.SubprocessError):
                st["proc"].kill()
        return True

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

    def copy_conversation(self):
        """열려 있는 대화의 글(나 / Claude)만 시간 순서대로 클립보드에 복사한다. 도구 호출은 뺀다."""
        if not self._cur:
            return {"ok": False, "error": "대화를 먼저 선택하십시오"}
        blocks = []
        for role, ts, parts in self._cur["msgs"]:
            text = "\n\n".join(x.strip() for k, x in parts if k == "text" and x.strip())
            text = re.sub(r"```choices[\s\S]*?```", "", text).strip()   # 대화창이 버튼으로 그리는 선택 블록은 복사에서 뺀다
            if text:
                blocks.append(f"[{'나' if role == 'user' else 'Claude'}]  {ts}\n{text}")
        if not blocks:
            return {"ok": False, "error": "복사할 대화 글이 없습니다"}
        out = "\n\n".join(blocks)
        if not clipboard_set(out):
            return {"ok": False, "error": "클립보드에 복사하지 못했습니다"}
        return {"ok": True, "n": len(blocks), "chars": len(out)}

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

    def get_models(self):
        return MODELS

    def get_efforts(self):
        return EFFORTS

    def get_limits(self):
        v = read_settings().get("limits")
        return v if isinstance(v, dict) else None

    def get_commands(self):
        """입력창 자동완성용 단축어 목록. 마지막 대화에서 받은 목록(스킬 포함)과 사용자 폴더의 직접 만든 단축어를 합친다."""
        cache = read_settings().get("cmd_cache") or {}
        names = []
        for n in list(cache.get("skills") or []) + scan_user_commands() + scan_plugin_commands() + \
                [c for c in cache.get("commands") or [] if c not in BUILTIN_SLASH]:
            if isinstance(n, str) and n and n not in BUILTIN_SLASH and n not in names:
                names.append(n)
        return names

    def health(self):
        """로그인과 인터넷 연결 점검(읽기만 한다). net: 인터넷, login: True/False/None(확인 못 함)"""
        net = net_ok()
        login = None
        exe = find_claude()
        if exe and net:
            try:
                r = subprocess.run([exe, "auth", "status"], capture_output=True, timeout=15, creationflags=NO_WINDOW)
                login = parse_auth_status(r.stdout.decode("utf-8", "replace"))
            except (OSError, subprocess.SubprocessError):
                login = None
        return {"net": net, "login": login, "claude": bool(exe)}

    def check_update(self):
        """웹사이트의 version.json 을 읽어 새 버전이 있는지 본다. 보내는 정보는 없다(파일 한 개를 내려받기만 한다)."""
        if read_settings().get("update_check") is False:
            return None
        try:
            with urllib.request.urlopen(urllib.request.Request(UPDATE_URL, headers={"User-Agent": "ClaudeChatViewer/" + APP_VERSION}), timeout=5) as r:
                d = json.loads(r.read(4096).decode("utf-8", "replace"))
            latest = str(d.get("latest", ""))
            if latest and vtuple(latest) > vtuple(APP_VERSION):
                return {"latest": latest, "cur": APP_VERSION, "skipped": read_settings().get("update_skip") == latest}
        except Exception:
            pass
        return None

    def open_site(self):
        """다운로드 페이지를 기본 브라우저로 연다(주소는 코드에 박혀 있고, 받은 파일의 내용으로 바뀌지 않는다)."""
        try:
            webbrowser.open(SITE_URL)
            return True
        except Exception:
            return False

    def open_login(self):
        """사용자가 누르면 새 콘솔 창에서 Claude Code 를 연다. 거기서 사용자가 /login 을 입력해 로그인한다(로그인 자체는 사용자가 브라우저에서 한다)."""
        exe = find_claude()
        if not exe:
            return False
        try:
            subprocess.Popen([exe], cwd=str(Path.home()), creationflags=0x00000010 if os.name == "nt" else 0)  # CREATE_NEW_CONSOLE
            return True
        except OSError:
            return False

    def get_clipboard(self):
        return clipboard_get()

    def set_clipboard(self, text):
        return clipboard_set(text)

    # ---- 음성 대화: 내 PC 안에서 돌아가는 음성 인식(whisper.cpp) ----
    def voice_status(self):
        return voice.status()

    def voice_download(self):
        return voice.download()

    def voice_prepare(self):
        return voice.start()

    def voice_transcribe(self, b64):
        import base64
        try:
            return voice.transcribe(base64.b64decode(b64))
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def send_inquiry(self, message, contact=""):
        """문의 글을 개발자 서버로 보낸다. 보내는 것은 글·연락처(선택)·프로그램 버전·Windows 버전뿐이다."""
        message, contact = (message or "").strip(), (contact or "").strip()
        if not message:
            return {"ok": False, "error": "내용을 입력해 주십시오"}
        if len(message) > 3000:
            return {"ok": False, "error": "내용은 3000자까지 보낼 수 있습니다"}
        now = time.time()
        if now - getattr(self, "_last_inquiry", 0) < 20:
            return {"ok": False, "error": "방금 보냈습니다. 잠시 뒤에 다시 보내 주십시오"}
        fields = {"message": message, "version": APP_VERSION, "os": platform.platform()[:100]}
        if contact:
            fields["contact"] = contact[:200]
        body = json.dumps({"fields": {k: {"stringValue": v} for k, v in fields.items()}}).encode("utf-8")
        req = urllib.request.Request(INQUIRY_URL + "?key=" + INQUIRY_KEY, data=body,
                                     headers={"Content-Type": "application/json", "User-Agent": "ClaudeChatViewer/" + APP_VERSION})
        try:
            urllib.request.urlopen(req, timeout=15).read()
        except Exception as e:
            return {"ok": False, "error": "보내지 못했습니다. 인터넷 연결을 확인한 뒤 다시 시도해 주십시오 (" + str(e)[:60] + ")"}
        self._last_inquiry = now
        return {"ok": True}

    def get_setting(self, key):
        return read_settings().get(key)

    def set_setting(self, key, val):
        return save_setting(key, val)

    def rename_session(self, path, title):
        """대화 이름을 바꾼다. 대화 파일은 그대로 두고 대화창 설정에만 저장한다(빈 이름이면 원래 이름으로 되돌림)."""
        try:
            p = Path(path).resolve()
            if p.suffix != ".jsonl" or core.PROJECTS.resolve() not in p.parents:
                return {"ok": False, "error": "Claude Code 대화 폴더 밖의 파일은 바꿀 수 없습니다"}
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
                return {"ok": False, "error": "응답 중인 대화는 삭제할 수 없습니다"}
            if not recycle(str(p)):
                return {"ok": False, "error": "휴지통으로 옮기지 못했습니다(파일이 사용 중일 수 있습니다)"}
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
        """세션 파일의 마지막 수정 후 경과 초와 버전. 대화창이 마지막으로 본 버전과 다르고 방금 바뀌었다면 다른 곳에서 쓰는 중일 수 있다."""
        v = self._ver(path)
        return {"ver": v, "idle": (time.time() - v[0] / 1e9) if v else None}

    def send(self, text, mode, files=None, model=None, chrome=False, web=False, effort=None):
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "빈 메시지입니다"}
        if self._run and self._run["proc"].poll() is None:
            return {"ok": False, "error": "이미 응답을 기다리는 중입니다"}
        exe = find_claude()
        if not exe:
            return {"ok": False, "error": "claude 명령을 찾을 수 없습니다. Claude Code를 설치하고 로그인해 주십시오"}
        mode_args = list(MODE_ARGS.get(mode, MODE_ARGS["read"]))
        if "--allowedTools" in mode_args:                 # 켜 둔 기능의 도구만 허용 목록에 더한다(모두 허용 모드는 원래 전부 허용)
            i = mode_args.index("--allowedTools") + 1
            if chrome:
                mode_args[i] += ",mcp__claude-in-chrome"
            if web:
                mode_args[i] += ",WebSearch,WebFetch"
        args = [exe, "-p", "--output-format", "stream-json", "--verbose", *mode_args, *prompt_file_args()]
        if chrome:
            args.append("--chrome")
        if model in MODEL_IDS and model:                  # 목록에 있는 이름만 넘긴다(임의 문자열이 명령줄에 들어가지 않게)
            args += ["--model", model]
        if effort in EFFORT_IDS and effort:
            args += ["--effort", effort]
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
        run = {"proc": proc, "sid": sid, "path": path, "result": None, "stderr": "", "limit": None, "model": None}
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
                typ = ev.get("type")
                if typ == "result":
                    run["result"] = ev
                elif typ == "system" and ev.get("subtype") == "init":
                    run["model"] = ev.get("model")
                    cmds = [c for c in (ev.get("slash_commands") or []) if isinstance(c, str)]
                    skills = [c for c in (ev.get("skills") or []) if isinstance(c, str)]
                    if cmds or skills:                     # 다음에 열었을 때 바로 자동완성이 되도록 저장
                        save_setting("cmd_cache", {"commands": cmds, "skills": skills})
                elif typ == "rate_limit_event":
                    info = ev.get("rate_limit_info") or {}
                    wins = {k: {"u": v.get("utilization"), "r": v.get("resetsAt")}
                            for k, v in (info.get("unifiedWindows") or {}).items() if isinstance(v, dict)}
                    if wins:                                   # 전체 한도 대비 사용률: 마지막으로 받은 값을 기억해 둔다
                        save_setting("limits", {"at": time.time(), "windows": wins})
                    if info.get("status") not in (None, "allowed"):
                        run["limit"] = info

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
        kind = None
        if error:
            res = r["result"] or {}
            kind = classify_error(error + " " + r["stderr"][-400:], res.get("api_error_status"))
            if kind == "other" and r["limit"]:
                kind = "limit"
        return {"running": running, "path": r["path"], "ver": ver, "error": error, "kind": kind,
                "model": r.get("model")}

    def new_window(self, path=None):
        """대화창을 하나 더 띄운다(별도 프로그램으로 실행되므로 창마다 Claude를 따로 돌릴 수 있다). path 가 있으면 그 대화를 연다."""
        env = dict(os.environ, CCV_ALLOW_MULTIPLE="1", PYINSTALLER_RESET_ENVIRONMENT="1")
        cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
        if path:
            try:
                p = Path(path).resolve()
                if p.suffix != ".jsonl" or core.PROJECTS.resolve() not in p.parents or not p.is_file():
                    return {"ok": False, "error": "열 수 없는 대화입니다"}
            except OSError:
                return {"ok": False, "error": "열 수 없는 대화입니다"}
            cmd.append(str(p))
        try:
            subprocess.Popen(cmd, env=env, close_fds=True,
                             creationflags=(0x00000008 | 0x00000200) if os.name == "nt" else 0)   # DETACHED_PROCESS | NEW_PROCESS_GROUP
        except OSError as e:
            return {"ok": False, "error": "새 창을 열지 못했습니다 (" + str(e)[:60] + ")"}
        return {"ok": True}

    def stop(self):
        r = self._run
        if r and r["proc"].poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(r["proc"].pid), "/T", "/F"], creationflags=NO_WINDOW,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                r["proc"].terminate()

    def preview_file(self, idx):
        """파일 탭 미리보기. 대화에 나온 파일만, 읽기 전용으로, 크기를 제한해서 보여 준다."""
        try:
            p = self._fp(idx)
        except (TypeError, KeyError, IndexError, AttributeError):
            return {"ok": False, "error": "파일을 찾지 못했습니다"}
        if not p or not os.path.isfile(p):
            return {"ok": False, "error": "현재 이 경로에 파일이 없습니다"}
        ext = os.path.splitext(p)[1].lower()
        size = os.path.getsize(p)
        img = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
               ".webp": "image/webp", ".bmp": "image/bmp", ".avif": "image/avif", ".jfif": "image/jpeg", ".ico": "image/x-icon", ".svg": "image/svg+xml"}
        try:
            if ext in img:
                if size > 8 * 1024 * 1024:
                    return {"ok": False, "error": "이미지가 너무 커서 미리볼 수 없습니다 (8MB 초과)"}
                with open(p, "rb") as f:
                    return {"ok": True, "kind": "image", "name": os.path.basename(p),
                            "src": "data:" + img[ext] + ";base64," + base64.b64encode(f.read()).decode("ascii")}
            if ext in OFFICE_KINDS:
                if size > 50 * 1024 * 1024:
                    return {"ok": False, "error": "파일이 너무 커서 미리볼 수 없습니다 (50MB 초과). \"현재 파일 열기\"를 쓰십시오"}
                try:
                    text = "\n".join(office_text(p, ext))
                except (zipfile.BadZipFile, KeyError, ValueError, ET.ParseError, RuntimeError):
                    return {"ok": False, "error": "열 수 없는 파일입니다. 암호가 걸렸거나 손상되었을 수 있습니다. \"현재 파일 열기\"를 쓰십시오"}
                if not text.strip():
                    return {"ok": False, "error": "뽑을 글자가 없습니다. \"현재 파일 열기\"를 쓰십시오"}
                cut = len(text) > 300 * 1024
                return {"ok": True, "kind": "text", "name": os.path.basename(p), "text": text[:300 * 1024],
                        "truncated": cut, "size": size, "lang": OFFICE_KINDS[ext] + " (글자만, 모양은 현재 파일 열기로 확인)"}
            if ext in OLD_OFFICE:
                return {"ok": False, "error": "옛 형식(" + ext + ")은 미리볼 수 없습니다. \"현재 파일 열기\"를 쓰십시오"}
            if ext == ".pdf":
                if size > 20 * 1024 * 1024:
                    return {"ok": False, "error": "PDF가 너무 커서 미리볼 수 없습니다 (20MB 초과). \"현재 파일 열기\"를 쓰십시오"}
                with open(p, "rb") as f:
                    return {"ok": True, "kind": "pdf", "name": os.path.basename(p),
                            "b64": base64.b64encode(f.read()).decode("ascii")}
            with open(p, "rb") as f:
                raw = f.read((2 * 1024 * 1024) if ext in (".html", ".htm") else 300 * 1024)
        except OSError as e:
            return {"ok": False, "error": "파일을 읽지 못했습니다 (" + str(e)[:60] + ")"}
        if b"\0" in raw[:4096]:
            return {"ok": False, "error": "글자 파일이 아니라서 미리볼 수 없습니다. \"현재 파일 열기\"를 쓰십시오"}
        kind = "html" if ext in (".html", ".htm") else "md" if ext in (".md", ".markdown") else "text"
        return {"ok": True, "kind": kind, "name": os.path.basename(p), "text": raw.decode("utf-8", errors="replace"),
                "truncated": size > len(raw), "size": size, "lang": PV_LANGS.get(ext, "")}

    def edit_open(self, idx):
        """파일 탭의 글자 파일을 옆 편집 창으로 연다. 대화에 나온 파일만, 글자 파일만, 2MB까지."""
        try:
            p = self._fp(idx)
        except (TypeError, KeyError, IndexError, AttributeError):
            return {"ok": False, "error": "파일을 찾지 못했습니다"}
        if not p or not os.path.isfile(p):
            return {"ok": False, "error": "현재 이 경로에 파일이 없습니다"}
        return self._edit_read(p)

    def _edit_read(self, p):
        if not p or not os.path.isfile(p):
            return {"ok": False, "error": "현재 이 경로에 파일이 없습니다"}
        ext = os.path.splitext(p)[1].lower()
        if ext in OFFICE_KINDS or ext in OLD_OFFICE or ext in (".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico",
                                                               ".zip", ".exe", ".dll", ".7z", ".mp3", ".mp4", ".wav"):
            return {"ok": False, "error": "글자 파일이 아니라서 편집 창으로 열 수 없습니다. 미리보기나 \"현재 파일 열기\"를 쓰십시오"}
        try:
            size = os.path.getsize(p)
            if size > 2 * 1024 * 1024:
                return {"ok": False, "error": "파일이 너무 커서 편집 창으로 열 수 없습니다 (2MB 초과)"}
            with open(p, "rb") as f:
                raw = f.read()
            mt = os.stat(p).st_mtime_ns
        except OSError as e:
            return {"ok": False, "error": "파일을 읽지 못했습니다 (" + str(e)[:60] + ")"}
        if b"\0" in raw[:4096]:
            return {"ok": False, "error": "글자 파일이 아니라서 편집 창으로 열 수 없습니다"}
        enc = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            try:
                enc, text = "cp949", raw.decode("cp949")
            except UnicodeDecodeError:
                return {"ok": False, "error": "글자 부호를 알 수 없어 편집 창으로 열 수 없습니다 (UTF-8, CP949만 지원)"}
        eol = "\r\n" if "\r\n" in text else "\n"
        self._edit_paths[os.path.normcase(os.path.abspath(p))] = p
        return {"ok": True, "path": p, "name": os.path.basename(p), "text": text.replace("\r\n", "\n"),
                "enc": enc, "eol": eol, "mtime": str(mt), "lang": PV_LANGS.get(ext, "")}

    def edit_reload(self, path):
        """편집 창으로 이미 연 파일을 디스크의 현재 내용으로 다시 읽는다."""
        p = self._edit_paths.get(os.path.normcase(os.path.abspath(str(path))))
        if not p:
            return {"ok": False, "error": "편집 창으로 연 파일이 아닙니다"}
        return self._edit_read(p)

    def edit_save(self, path, text, base_mtime, enc, eol, force=False):
        """편집 창의 내용을 저장한다. edit_open 으로 연 파일만. 디스크에서 그 사이 바뀌었으면 덮어쓰지 않고 알린다."""
        key = os.path.normcase(os.path.abspath(str(path)))
        p = self._edit_paths.get(key)
        if not p:
            return {"ok": False, "error": "편집 창으로 연 파일이 아닙니다"}
        if enc not in ("utf-8", "utf-8-sig", "cp949") or eol not in ("\n", "\r\n") or not isinstance(text, str):
            return {"ok": False, "error": "저장 형식이 올바르지 않습니다"}
        try:
            if os.path.exists(p) and not force and str(os.stat(p).st_mtime_ns) != str(base_mtime):
                return {"ok": False, "conflict": True, "error": "열어 둔 뒤에 디스크의 파일이 바뀌었습니다"}
            data = text.replace("\r\n", "\n").replace("\n", eol).encode(enc)
        except UnicodeEncodeError:
            return {"ok": False, "error": "이 파일의 글자 부호(" + enc + ")로 표현할 수 없는 글자가 있습니다"}
        except OSError as e:
            return {"ok": False, "error": "저장하지 못했습니다 (" + str(e)[:60] + ")"}
        tmp = p + ".ccv-tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, p)
            return {"ok": True, "mtime": str(os.stat(p).st_mtime_ns)}
        except OSError as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return {"ok": False, "error": "저장하지 못했습니다 (" + str(e)[:60] + ")"}

    def open_path(self, idx, folder):
        p = self._fp(idx)
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
        close_splash()
        if message_box("화면을 그리는 Microsoft Edge WebView2 런타임을 찾지 못했습니다.\n설치 페이지를 여시겠습니까?\n(아니오를 누르면 그대로 실행을 시도합니다)", 0x24) == 6:  # MB_YESNO|ICONQUESTION, IDYES
            webbrowser.open(WEBVIEW2_URL)
            sys.exit(0)
    api = Api()
    api._window = webview.create_window(TITLE, (BASE / "ui.html").as_uri(), js_api=api,
                                       width=1280, height=800, min_size=(900, 560), background_color="#0f1115")
    api._window.events.loaded += close_splash  # 화면이 그려지면 '여는 중' 창을 닫는다
    api._window.events.closed += api.stop  # 창을 닫으면 응답 중이던 claude도 같이 끝낸다
    api._window.events.closed += voice.stop  # 음성 인식 엔진도 같이 끝낸다
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
        close_splash()
        message_box("창을 열지 못했습니다.\n\n" + str(e)[:400], 0x10)
        raise
