"""Claude Code 대화 뷰어: pywebview 창에 ui.html을 띄우고 core의 파싱 결과를 JS에 넘긴다."""
import os
import re
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

import webview

import core
import export

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
CATS = ("files", "cmds", "others")


class Api:
    def __init__(self):
        self._window = None
        self._cur = None
        self._cur_path = None
        self._title = ""
        self._initial = sys.argv[1] if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]) else None

    def get_initial(self):
        if not self._initial:
            return None
        title, ts = core.session_info(Path(self._initial))
        return {"path": self._initial, "title": title, "date": core.local_time(ts)}

    def list_sessions(self):
        files = sorted(core.PROJECTS.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True) \
            if core.PROJECTS.exists() else []
        out = []
        for p in files:
            title, ts = core.session_info(p)
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

    def pick_file(self):
        dlg = getattr(webview, "FileDialog", None)
        mode = dlg.OPEN if dlg else webview.OPEN_DIALOG
        r = self._window.create_file_dialog(mode, file_types=("Claude 세션 (*.jsonl)",))
        if not r:
            return None
        title, ts = core.session_info(Path(r[0]))
        return {"path": r[0], "title": title, "date": core.local_time(ts)}

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
    api = Api()
    api._window = webview.create_window("Claude Code 대화 뷰어 v2.2", (BASE / "ui.html").as_uri(), js_api=api,
                                       width=1280, height=800, min_size=(900, 560), background_color="#0f1115")
    webview.start()
