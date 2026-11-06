"""세션 jsonl 파싱과 HTML/TXT 변환."""
import difflib
import html
import json
import os
import re
from datetime import datetime
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
COMPACT_HEAD = "This session is being continued from a previous conversation"
# 사용자가 쓴 글이 아니라 Claude Code 가 자동으로 붙이는 안내 문구(맨 앞에 붙거나 단독으로 기록된다)
NOTICE_RE = re.compile(r"^\s*(Your response above was cut off mid-stream\.[^\n]*|\[Request interrupted by user[^\]\n]*\])[ \t]*\n?", re.I)
REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
# 백그라운드 작업이 끝났을 때 하네스가 사용자 메시지처럼 끼워 넣는 알림. 내가 친 글이 아니므로 Claude Code 쪽 안내로 보여 준다
TASKNOTE_RE = re.compile(r"<task-notification>(.*?)</task-notification>", re.S)
_TN_TAG = re.compile(r"<(summary|status)>(.*?)</\1>", re.S)


def task_notice(body):
    d = {k: v.strip() for k, v in _TN_TAG.findall(body)}
    head = "백그라운드 작업 알림"
    if d.get("status"):
        head += " · " + d["status"]
    if d.get("summary"):
        head += ": " + d["summary"]
    return head + chr(10) * 2 + body.strip()
FILE_TOOLS = {"Write": "생성", "Edit": "수정", "MultiEdit": "수정", "NotebookEdit": "수정", "Read": "읽기"}
CMD_TOOLS = {"Bash", "PowerShell"}
VIEW_LIMIT = 100_000


# ---------- 파싱 ----------

def read_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except ValueError:
                    pass


def plain_text(path):
    """대화 검색용: 사람이 읽는 글(내 말과 Claude의 답)만 모은다. 도구 결과와 시스템 안내는 뺀다."""
    out = []
    for r in read_lines(path):
        if r.get("type") not in ("user", "assistant") or r.get("isCompactSummary"):
            continue
        m = r.get("message")
        c = m.get("content") if isinstance(m, dict) else None
        x = text_of(c)
        if x:
            x = REMINDER_RE.sub("", TASKNOTE_RE.sub("", x)).strip()
            if x and not x.lstrip().startswith(COMPACT_HEAD):
                out.append(x)
    return chr(10).join(out)


def local_time(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return ts or ""


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def session_info(path):
    title, first, ts = "", "", ""
    for r in read_lines(path):
        if r.get("type") == "ai-title" and r.get("aiTitle"):
            title = r["aiTitle"]
        if not first and r.get("type") == "user" and not r.get("isMeta"):
            first = REMINDER_RE.sub("", text_of(r.get("message", {}).get("content"))).strip()
            ts = r.get("timestamp", "")
    return title or first[:40].replace("\n", " ") or path.stem, ts


def parse(path, with_reminders=False):
    """-> dict(msgs, files, cmds, others). msgs: [(role, ts, [(kind, payload)])], kind: text|thinking|compact|sys|tool"""
    tools, msgs = {}, []
    for r in read_lines(path):
        t = r.get("type")
        m = r.get("message")
        if t not in ("user", "assistant") or not isinstance(m, dict):
            continue
        ts = local_time(r.get("timestamp", ""))
        c = m.get("content")
        parts = []
        if isinstance(c, str):
            parts.append(("text", c))
        elif isinstance(c, list):
            for b in c:
                k = b.get("type")
                if k == "text":
                    parts.append(("text", b.get("text", "")))
                elif k == "thinking" and b.get("thinking"):
                    parts.append(("thinking", b["thinking"]))
                elif k == "tool_use":
                    tool = {"id": b.get("id"), "name": b.get("name", ""), "input": b.get("input", {}),
                            "ts": ts, "result": None, "error": False}
                    tools[tool["id"]] = tool
                    parts.append(("tool", tool))
                elif k == "tool_result":
                    tool = tools.get(b.get("tool_use_id"))
                    res = b.get("content")
                    if isinstance(res, list):
                        res = "\n".join(x.get("text", "") for x in res if isinstance(x, dict))
                    if tool:
                        tool["result"], tool["error"] = str(res), bool(b.get("is_error"))
                    else:
                        parts.append(("text", f"[도구 결과]\n{res}"))
        if t == "user" and (r.get("isCompactSummary") or any(
                k == "text" and x.lstrip().startswith(COMPACT_HEAD) for k, x in parts)):
            # /compact(자동 압축 포함) 뒤에 붙는 요약은 내가 보낸 글이 아니라 Claude Code가 처리한 내용이다
            parts = [("compact", "\n\n".join(x for k, x in parts if k == "text"))]
            t = "assistant"
        if not with_reminders:
            parts = [(k, REMINDER_RE.sub("", x).strip() if k == "text" else x) for k, x in parts]
        parts = [(k, x) for k, x in parts if k == "tool" or x.strip()]
        if t == "user":
            notice = []
            kept = []
            for k, x in parts:
                if k == "text":
                    for m1 in TASKNOTE_RE.finditer(x):
                        notice.append(("sys", task_notice(m1.group(1))))
                    x = TASKNOTE_RE.sub("", x).strip()
                    if not x:
                        continue
                kept.append((k, x))
            parts = kept
            if parts and parts[0][0] == "text":
                m0 = NOTICE_RE.match(parts[0][1])
                if m0:   # 맨 앞의 자동 안내 문구는 따로 떼어 Claude Code 쪽 안내로 보여 준다
                    rest = parts[0][1][m0.end():].strip()
                    notice.append(("sys", m0.group(1).strip()))
                    parts = ([("text", rest)] if rest else []) + parts[1:]
            if notice:
                if msgs and msgs[-1][0] == "claude":
                    msgs[-1][2].extend(notice)
                else:
                    msgs.append(("claude", ts, notice))
        if parts:
            role = "user" if t == "user" else "claude"
            if msgs and msgs[-1][0] == role:  # 같은 화자의 연속 기록은 한 메시지로 합친다
                msgs[-1][2].extend(parts)
            else:
                msgs.append((role, ts, parts))
    files, cmds, others = [], [], []
    for _, _, parts in msgs:
        for k, x in parts:
            if k != "tool":
                continue
            if x["name"] in FILE_TOOLS:
                files.append(x)
            elif x["name"] in CMD_TOOLS:
                cmds.append(x)
            else:
                others.append(x)
    return {"msgs": msgs, "files": files, "cmds": cmds, "others": others}


# ---------- 텍스트 표현 ----------

def file_path_of(t):
    i = t["input"]
    return i.get("file_path") or i.get("notebook_path") or ""


def tool_summary(t):
    i = t["input"]
    for key in ("file_path", "notebook_path", "command", "query", "url", "description", "pattern", "prompt", "skill"):
        if i.get(key):
            return str(i[key]).strip().split("\n")[0][:120]
    return ""


def diff_text(old, new):
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "변경 전", "변경 후"))


def result_block(t):
    if t["result"] is None:
        return "(결과 기록 없음)"
    return ("[오류]\n" if t["error"] else "") + t["result"]


def file_detail(t):
    i, name = t["input"], t["name"]
    head = f"{FILE_TOOLS[name]} · {file_path_of(t)}\n{t['ts']}\n{'-' * 50}\n"
    if name == "Write":
        return head + i.get("content", "")
    if name == "Edit":
        return head + (diff_text(i.get("old_string", ""), i.get("new_string", "")) or "(변경 없음)")
    if name == "MultiEdit":
        return head + "\n".join(diff_text(e.get("old_string", ""), e.get("new_string", "")) for e in i.get("edits", []))
    if name == "NotebookEdit":
        return head + i.get("new_source", "")
    return head + result_block(t)


def cmd_detail(t):
    return f"[{t['name']}] {t['ts']}\n$ {t['input'].get('command', '')}\n{'-' * 50}\n{result_block(t)}"


def generic_detail(t):
    return (f"[{t['name']}] {t['ts']}\n{json.dumps(t['input'], ensure_ascii=False, indent=2)}\n"
            f"{'-' * 50}\n{result_block(t)}")


def tool_detail(t):
    if t["name"] in FILE_TOOLS:
        return file_detail(t)
    if t["name"] in CMD_TOOLS:
        return cmd_detail(t)
    return generic_detail(t)


def clip(s):
    return s if len(s) <= VIEW_LIMIT else s[:VIEW_LIMIT] + f"\n\n... (이후 {len(s) - VIEW_LIMIT:,}자 생략, TXT/HTML 저장본에는 전체 포함)"
