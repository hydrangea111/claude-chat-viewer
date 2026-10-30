"""세션 데이터를 TXT / 자체완결형 HTML 문서로 내보낸다."""
import html
import re
import unicodedata
from collections import Counter
from datetime import datetime

import core

ROLE = {"user": "사용자", "claude": "Claude"}
SEP = "=" * 72
THIN = "-" * 72


def _stats(data):
    msgs = data["msgs"]
    roles = Counter(m[0] for m in msgs)
    acts = Counter(core.FILE_TOOLS[t["name"]] for t in data["files"])
    errs = sum(1 for t in data["cmds"] if t["error"])
    times = [m[1] for m in msgs if m[1]]
    return {
        "start": min(times) if times else "", "end": max(times) if times else "",
        "msgs": len(msgs), "user": roles["user"], "claude": roles["claude"],
        "files": len(data["files"]), "acts": acts, "cmds": len(data["cmds"]), "errs": errs,
        "others": len(data["others"]),
    }


def _numbering(data):
    """도구 호출에 대화 순서대로 T001.. 번호를 매긴다. {id(tool dict): n}"""
    n, out = 0, {}
    for _, _, parts in data["msgs"]:
        for k, x in parts:
            if k == "tool":
                n += 1
                out[id(x)] = n
    return out


def _width(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _pad(s, w):
    return s + " " * max(0, w - _width(s))


# ---------------------------------------------------------------- TXT

def to_txt(data, title, sid=""):
    st, num = _stats(data), _numbering(data)
    acts = ", ".join(f"{k} {v}" for k, v in st["acts"].items()) or "없음"
    L = [SEP, " Claude Code 대화 기록", SEP,
         f" 제목        : {title}",
         f" 세션 ID     : {sid or '-'}",
         f" 기간        : {st['start']} ~ {st['end']}",
         f" 메시지      : {st['msgs']}개 (사용자 {st['user']} / Claude {st['claude']})",
         f" 파일 작업   : {st['files']}건 ({acts})",
         f" 실행한 명령 : {st['cmds']}건 (오류 {st['errs']}건)",
         f" 기타 도구   : {st['others']}건",
         f" 내보낸 시각 : {datetime.now():%Y-%m-%d %H:%M:%S}",
         SEP, "", "[목차]", " 1. 대화", " 2. 파일 작업 목록", " 3. 실행한 명령", " 4. 기타 도구 사용", "",
         "※ 대화 속 '도구 호출 T###'은 Claude가 실행한 작업이며, 2~4번 목록의 번호와 같습니다.",
         "※ 파일 내용은 Claude Code가 기록한 '당시 내용'이며 현재 디스크의 파일과 다를 수 있습니다.", "",
         SEP, " 1. 대화", SEP, ""]

    def block(text, indent="  "):
        return [indent + ln if ln else "" for ln in text.split("\n")]

    for i, (role, ts, parts) in enumerate(data["msgs"], 1):
        L.append(f"#{i:03d}  [{ROLE[role]}]  {ts}")
        L.append(THIN)
        for k, x in parts:
            if k == "text":
                L += block(x)
            elif k == "thinking":
                L += ["  [생각]"] + block(x, "    ")
            else:
                head = f"  [도구 호출 T{num[id(x)]:03d}] {x['name']}"
                if x["error"]:
                    head += "  (오류)"
                L += ["", head] + block(core.tool_detail(x), "  | ") + [""]
        L += ["", ""]

    def table(rows, empty="(없음)"):
        return rows or [f" {empty}"]

    L += [SEP, f" 2. 파일 작업 목록 ({st['files']}건)", SEP]
    L += table([f" T{num[id(t)]:03d}  {t['ts']}  {_pad(core.FILE_TOOLS[t['name']], 4)}  {core.file_path_of(t)}"
                for t in data["files"]])
    L += ["", SEP, f" 3. 실행한 명령 ({st['cmds']}건)", SEP]
    L += table([f" T{num[id(t)]:03d}  {t['ts']}  {'오류' if t['error'] else 'OK  '}  [{t['name']}]  "
                f"{(t['input'].get('command') or '').strip().splitlines()[0][:150] if (t['input'].get('command') or '').strip() else ''}"
                for t in data["cmds"]])
    L += ["", SEP, f" 4. 기타 도구 사용 ({st['others']}건)", SEP]
    L += table([f" T{num[id(t)]:03d}  {t['ts']}  {t['name']}  {core.tool_summary(t)}" for t in data["others"]])
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- HTML

CSS = """
:root{--bg:#f6f5f2;--panel:#fff;--line:#e3e0d9;--text:#1f1d1a;--dim:#7a766d;--accent:#c8643c;--chip:#f1efe9;--code:#f4f2ed;
--ok:#2f9e63;--err:#d44a4a;--warn:#c78a1d;--add:#e3f5e8;--del:#fbe6e6;--shadow:0 1px 2px rgba(0,0,0,.05),0 4px 14px rgba(0,0,0,.05)}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1115;--panel:#171a20;--line:#262a33;--text:#e8e6e1;--dim:#8b8f99;
--accent:#e0805a;--chip:#1e222a;--code:#11141a;--add:#12301f;--del:#3a1a1c;--shadow:none}}
:root[data-theme=dark]{--bg:#0f1115;--panel:#171a20;--line:#262a33;--text:#e8e6e1;--dim:#8b8f99;--accent:#e0805a;--chip:#1e222a;--code:#11141a;--add:#12301f;--del:#3a1a1c;--shadow:none}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:64px}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.65 "Segoe UI","Malgun Gothic","Apple SD Gothic Neo",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:0 20px 80px}
.hero{padding:40px 0 18px}.hero h1{margin:0 0 6px;font-size:26px;letter-spacing:-.4px;line-height:1.3}
.hero .sid{color:var(--dim);font-size:12px;font-family:Consolas,monospace}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:8px 14px;box-shadow:var(--shadow)}
.stat b{display:block;font-size:18px;line-height:1.2}.stat span{font-size:12px;color:var(--dim)}
nav{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);display:flex;gap:2px;align-items:center;padding:6px 0;margin:0 -20px;padding-left:20px;padding-right:20px}
nav a{color:var(--dim);text-decoration:none;padding:7px 12px;border-radius:9px;font-weight:600;font-size:13.5px}
nav a:hover{background:var(--chip);color:var(--text)}nav .sp{flex:1}
nav button{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:9px;padding:5px 11px;font:inherit;font-size:12.5px;cursor:pointer;margin-left:6px}
nav button:hover{border-color:var(--accent);color:var(--accent)}
h2{font-size:18px;margin:44px 0 14px;letter-spacing:-.2px}h2 small{color:var(--dim);font-weight:400;font-size:13px;margin-left:6px}
.note{color:var(--dim);font-size:12.5px;margin:-6px 0 14px}
.msg{display:flex;gap:12px;margin:22px 0 0}.msg.user{flex-direction:row-reverse}
.av{width:30px;height:30px;border-radius:10px;flex-shrink:0;display:grid;place-items:center;font-size:12px;font-weight:700;color:#fff;background:#5b6270}
.msg.claude .av{background:linear-gradient(135deg,var(--accent),#e9a46f)}
.body{max-width:calc(100% - 44px);min-width:0}.msg.user .body{display:flex;flex-direction:column;align-items:flex-end}
.bubble{padding:11px 16px;border-radius:16px;white-space:pre-wrap;overflow-wrap:anywhere}
.msg.claude .bubble{background:var(--panel);border:1px solid var(--line);border-top-left-radius:5px;box-shadow:var(--shadow)}
.msg.user .bubble{background:var(--accent);color:#fff;border-top-right-radius:5px}
.bubble+.bubble,.bubble+details,details+.bubble,details+details{margin-top:8px}
.meta{font-size:11px;color:var(--dim);margin-top:5px}.meta a{color:inherit}
code{background:var(--code);padding:1px 6px;border-radius:5px;font:12.5px Consolas,monospace}
.msg.user .bubble code{background:rgba(255,255,255,.22)}
.bubble pre{background:var(--code);color:var(--text);padding:12px 14px;border-radius:10px;overflow:auto;margin:8px 0 2px;font:12.5px/1.55 Consolas,monospace;white-space:pre}
.bubble pre code{background:none;padding:0}
details{background:var(--chip);border:1px solid var(--line);border-radius:12px;font-size:13px;max-width:100%}
details.think{background:transparent;border-style:dashed}
summary{cursor:pointer;padding:7px 12px;display:flex;gap:8px;align-items:center;list-style:none;user-select:none}
summary::-webkit-details-marker{display:none}summary:before{content:"▸";color:var(--dim);font-size:11px}
details[open]>summary:before{content:"▾"}
.nm{font-family:Consolas,monospace;font-weight:700;font-size:12px;color:var(--accent);flex-shrink:0}
details.err .nm{color:var(--err)}.sm{color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.tid{margin-left:auto;color:var(--dim);font:11px Consolas,monospace;flex-shrink:0;padding-left:8px}
.code{margin:0;padding:10px 0;background:var(--code);border-top:1px solid var(--line);border-radius:0 0 12px 12px;overflow:auto;max-height:480px;font:12px/1.6 Consolas,monospace}
.code div{padding:0 14px;white-space:pre-wrap;overflow-wrap:anywhere;min-height:1.6em}
.code .add{background:var(--add)}.code .del{background:var(--del)}.code .hunk{color:var(--accent)}
table{width:100%;border-collapse:collapse;font-size:13px;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:var(--shadow)}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--chip);color:var(--dim);font-size:12px}tr:last-child td{border-bottom:0}
td.path{font-family:Consolas,monospace;font-size:12px;overflow-wrap:anywhere}td a{color:var(--accent);text-decoration:none;font-family:Consolas,monospace;font-size:12px}
.badge{font-size:11px;font-weight:700;padding:2px 9px;border-radius:20px;white-space:nowrap}
.b-생성{background:rgba(47,158,99,.16);color:var(--ok)}.b-수정{background:rgba(199,138,29,.18);color:var(--warn)}.b-읽기{background:var(--chip);color:var(--dim)}
.b-OK{background:rgba(47,158,99,.16);color:var(--ok)}.b-오류{background:rgba(212,74,74,.16);color:var(--err)}.b-none{background:var(--chip);color:var(--dim)}
.cmd{margin:6px 0}.cmd summary .sm{font-family:Consolas,monospace;font-size:12px;color:var(--text)}
footer{margin-top:60px;color:var(--dim);font-size:12px;text-align:center}
@media print{nav,.noprint{display:none}body{background:#fff}details>*:not(summary){display:block}.msg,details,table{break-inside:avoid}}
@media(max-width:600px){.msg.user .bubble,.msg.claude .bubble{max-width:100%}}
"""

JS = """
const all=s=>document.querySelectorAll(s);
function setAll(o){all('details').forEach(d=>d.open=o)}
document.getElementById('open').onclick=()=>setAll(true);
document.getElementById('close').onclick=()=>setAll(false);
document.getElementById('theme').onclick=()=>{const r=document.documentElement;
 const dark=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme:dark)').matches;
 r.dataset.theme=dark?'light':'dark'};
if(location.hash){const t=document.querySelector(location.hash);if(t&&t.tagName==='DETAILS')t.open=true}
addEventListener('hashchange',()=>{const t=document.querySelector(location.hash);if(t&&t.tagName==='DETAILS')t.open=true});
"""


def _e(s):
    return html.escape(str(s))


def _md(s):
    """코드블록, `인라인`, **굵게**, # 제목 만 지원하는 가벼운 마크다운."""
    out = []
    for i, seg in enumerate(s.split("```")):
        if i % 2:
            nl = seg.find("\n")
            body = seg[nl + 1:] if 0 <= nl < 20 else seg
            out.append(f"<pre><code>{_e(body)}</code></pre>")
            continue
        seg = _e(seg)
        seg = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", seg)
        seg = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", seg)
        seg = re.sub(r"(?m)^#{1,4} (.+)$", r"<b>\1</b>", seg)
        out.append(seg)
    return re.sub(r"</pre>\n", "</pre>", "".join(out))


def _code(text, diff):
    rows = []
    for ln in text.split("\n"):
        cls = ""
        if diff:
            if ln.startswith("+") and not ln.startswith("+++"):
                cls = "add"
            elif ln.startswith("-") and not ln.startswith("---"):
                cls = "del"
            elif ln.startswith("@@"):
                cls = "hunk"
        rows.append(f'<div class="{cls}">{_e(ln) or " "}</div>')
    return f'<div class="code">{"".join(rows)}</div>'


def _tool(x, n):
    diff = x["name"] in ("Edit", "MultiEdit")
    cls = "err" if x["error"] else ""
    return (f'<details id="t{n}" class="{cls}"><summary><span class="nm">{_e(x["name"])}</span>'
            f'<span class="sm">{_e(core.tool_summary(x))}</span><span class="tid">T{n:03d}</span></summary>'
            f'{_code(core.tool_detail(x), diff)}</details>')


def to_html(data, title, sid=""):
    st, num = _stats(data), _numbering(data)
    acts = " · ".join(f"{k} {v}" for k, v in st["acts"].items())
    stat = lambda b, s: f'<div class="stat"><b>{b}</b><span>{s}</span></div>'
    B = [f'<div class="hero"><h1>{_e(title)}</h1><div class="sid">{_e(sid)}</div><div class="stats">',
         stat(f"{st['start'][:10]}", f"{st['start'][11:16]} ~ {st['end'][5:16]}"),
         stat(st["msgs"], f"메시지 (사용자 {st['user']} · Claude {st['claude']})"),
         stat(st["files"], acts or "파일 작업"), stat(st["cmds"], f"명령 (오류 {st['errs']})"),
         stat(st["others"], "기타 도구"), "</div></div>",
         '<nav><a href="#chat">대화</a><a href="#files">파일</a><a href="#cmds">명령</a><a href="#others">기타</a>'
         '<span class="sp"></span><button id="open">모두 펼치기</button><button id="close">모두 접기</button>'
         '<button id="theme">테마</button></nav>',
         '<h2 id="chat">대화</h2>']
    for i, (role, ts, parts) in enumerate(data["msgs"], 1):
        inner = []
        for k, x in parts:
            if k == "text":
                inner.append(f'<div class="bubble">{_md(x)}</div>')
            elif k == "thinking":
                inner.append(f'<details class="think"><summary><span class="nm" style="font-family:inherit;color:var(--dim)">생각</span>'
                             f'<span class="sm">{_e(x[:80])}</span></summary>{_code(x, False)}</details>')
            else:
                inner.append(_tool(x, num[id(x)]))
        B.append(f'<div class="msg {role}" id="m{i}"><div class="av">{"나" if role == "user" else "C"}</div>'
                 f'<div class="body">{"".join(inner)}<div class="meta">#{i} · {_e(ts)}</div></div></div>')

    B.append(f'<h2 id="files">파일 작업<small>{st["files"]}건</small></h2>'
             '<div class="note">파일 내용은 Claude Code가 기록한 \'당시 내용\'이며 현재 디스크의 파일과 다를 수 있습니다.</div>')
    if data["files"]:
        B.append("<table><tr><th>호출</th><th>시각</th><th>동작</th><th>경로</th></tr>")
        for t in data["files"]:
            a = core.FILE_TOOLS[t["name"]]
            B.append(f'<tr><td><a href="#t{num[id(t)]}">T{num[id(t)]:03d}</a></td><td>{_e(t["ts"])}</td>'
                     f'<td><span class="badge b-{a}">{a}</span></td><td class="path">{_e(core.file_path_of(t))}</td></tr>')
        B.append("</table>")
    else:
        B.append("<p class='note'>기록이 없습니다.</p>")

    B.append(f'<h2 id="cmds">실행한 명령<small>{st["cmds"]}건</small></h2>')
    for t in data["cmds"]:
        n = num[id(t)]
        state = "오류" if t["error"] else ("none" if t["result"] is None else "OK")
        first = (t["input"].get("command") or "").strip().splitlines()
        B.append(f'<details class="cmd {"err" if t["error"] else ""}"><summary><span class="badge b-{state}">{"-" if state == "none" else state}</span>'
                 f'<span class="nm" style="color:var(--dim)">{_e(t["name"])}</span><span class="sm">{_e(first[0][:140] if first else "")}</span>'
                 f'<span class="tid">T{n:03d} · <a href="#t{n}">대화에서 보기</a></span></summary>{_code(core.cmd_detail(t), False)}</details>')
    if not data["cmds"]:
        B.append("<p class='note'>기록이 없습니다.</p>")

    B.append(f'<h2 id="others">기타 도구 사용<small>{st["others"]}건</small></h2>')
    if data["others"]:
        B.append("<table><tr><th>호출</th><th>시각</th><th>도구</th><th>요약</th></tr>")
        for t in data["others"]:
            B.append(f'<tr><td><a href="#t{num[id(t)]}">T{num[id(t)]:03d}</a></td><td>{_e(t["ts"])}</td>'
                     f'<td class="path">{_e(t["name"].replace("mcp__", ""))}</td><td>{_e(core.tool_summary(t))}</td></tr>')
        B.append("</table>")
    else:
        B.append("<p class='note'>기록이 없습니다.</p>")
    B.append(f'<footer>Claude Code 대화 뷰어로 내보냄 · {datetime.now():%Y-%m-%d %H:%M}</footer>')
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{_e(title)}</title><style>{CSS}</style></head>'
            f'<body><div class="wrap">{"".join(B)}</div><script>{JS}</script></body></html>')
