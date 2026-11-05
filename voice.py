"""음성 인식: 내 PC에서 돌아가는 whisper.cpp 서버로 말을 글자로 바꾼다(음성이 PC 밖으로 나가지 않는다).

처음 한 번만 엔진(약 9MB)과 한국어 모델(약 190MB)을 내려받는다. 두 파일 모두 고정된 주소에서 받고 SHA-256을 확인한다.
"""
import hashlib
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
import wave
import zipfile
from pathlib import Path

DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ClaudeChatViewer" / "voice"
BIN = DIR / "bin"
ENGINE = {
    "url": "https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-bin-x64.zip",
    "sha": "6ba69e3482d7826214f90a6a9c84ca07782aec1e1d0c6a7c30c994fd5d816ccb",
    "size": 8928640,
}
MODEL = {
    "name": "ggml-small-q5_1.bin",
    "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small-q5_1.bin",
    "sha": "ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb",
    "size": 190085487,
}
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
# 조용한 곳에서 whisper가 지어내는 대표적인 문장들(자막 학습 흔적)은 버린다
JUNK = ("시청해 주셔서", "시청해주셔서", "구독과 좋아요", "구독 좋아요", "자막 제공", "자막by", "MBC 뉴스", "다음 영상")

_lock = threading.Lock()
_prog = {"phase": "", "done": 0, "total": 0, "error": "", "running": False}
_proc = None
_port = 0


def model_path():
    return DIR / MODEL["name"]


def server_path():
    return BIN / "whisper-server.exe"


def ready():
    return server_path().exists() and model_path().exists() and model_path().stat().st_size == MODEL["size"]


def status():
    return {"ready": ready(), "engine": server_path().exists(), "model": model_path().exists(),
            "need_mb": 0 if ready() else round((0 if server_path().exists() else ENGINE["size"]) / 1e6 + (0 if model_path().exists() else MODEL["size"]) / 1e6),
            "prog": dict(_prog), "serving": bool(_proc and _proc.poll() is None)}


def _fetch(spec, dest, phase):
    """주소에서 받아 dest.part 에 쓰고, 크기와 SHA-256 이 맞을 때만 dest 로 옮긴다."""
    part = dest.with_name(dest.name + ".part")
    _prog.update(phase=phase, done=0, total=spec["size"])
    h = hashlib.sha256()
    req = urllib.request.Request(spec["url"], headers={"User-Agent": "ClaudeChatViewer"})
    with urllib.request.urlopen(req, timeout=30) as r, open(part, "wb") as f:
        while True:
            b = r.read(1 << 18)
            if not b:
                break
            f.write(b)
            h.update(b)
            _prog["done"] += len(b)
    if part.stat().st_size != spec["size"] or h.hexdigest() != spec["sha"]:
        part.unlink(missing_ok=True)
        raise RuntimeError("내려받은 파일이 올바르지 않습니다(크기 또는 해시가 다릅니다). 잠시 뒤 다시 시도해 주십시오.")
    part.replace(dest)


def _download():
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        BIN.mkdir(parents=True, exist_ok=True)
        if not server_path().exists():
            z = DIR / "engine.zip"
            _fetch(ENGINE, z, "엔진")
            with zipfile.ZipFile(z) as zf:
                for n in zf.namelist():
                    base = n.rsplit("/", 1)[-1]
                    if base == "whisper-server.exe" or base.lower().endswith(".dll"):  # 폴더 구조는 버리고 파일 이름만 쓴다
                        (BIN / base).write_bytes(zf.read(n))
            z.unlink(missing_ok=True)
        if not model_path().exists() or model_path().stat().st_size != MODEL["size"]:
            _fetch(MODEL, model_path(), "한국어 모델")
        _prog.update(phase="완료", error="")
    except Exception as e:
        _prog["error"] = str(e)[:300] or "내려받지 못했습니다"
    finally:
        _prog["running"] = False


def download():
    with _lock:
        if _prog["running"]:
            return True
        if ready():
            return True
        _prog.update(running=True, error="", phase="준비", done=0, total=0)
        threading.Thread(target=_download, daemon=True).start()
        return True


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait_port(port, proc, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            return False
        try:
            socket.create_connection(("127.0.0.1", port), 0.5).close()
            return True
        except OSError:
            time.sleep(0.3)
    return False


def _kill_stale():
    """앱이 비정상 종료돼 남은, 이 앱의 음성 인식 엔진만 정리한다(다른 프로그램의 whisper는 건드리지 않는다)."""
    if os.name != "nt":
        return
    try:
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='whisper-server.exe'\" | "
              "Where-Object { $_.ExecutablePath -eq '%s' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" % str(server_path()).replace("'", "''"))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=NO_WINDOW, timeout=15,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


_cleaned = False


def start():
    """서버가 없으면 띄운다(모델을 한 번 올려 두면 다음부터 빠르다). 성공하면 True."""
    global _proc, _port
    with _lock:
        if _proc and _proc.poll() is None:
            return True
        if not ready():
            return False
        global _cleaned
        if not _cleaned:
            _cleaned = True
            _kill_stale()
        port = _free_port()
        threads = max(2, min(8, (os.cpu_count() or 4) - 1))
        _proc = subprocess.Popen(
            [str(server_path()), "-m", str(model_path()), "-l", "ko", "--host", "127.0.0.1", "--port", str(port),
             "-t", str(threads), "-bs", "1", "-bo", "1", "-nt", "-sns", "--prompt", "한국어 대화입니다."],
            cwd=str(BIN), creationflags=NO_WINDOW, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _port = port
        if not _wait_port(port, _proc):
            stop()
            return False
        return True


def stop():
    global _proc
    p = _proc
    _proc = None
    if p and p.poll() is None:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], creationflags=NO_WINDOW,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                p.terminate()
        except Exception:
            pass


def _clean(text):
    t = (text or "").replace("\n", " ").strip()
    if len(t.replace(" ", "")) < 2:
        return ""
    if any(j in t for j in JUNK) and len(t) < 30:
        return ""
    return t


def transcribe(pcm16_bytes):
    """16kHz 모노 16비트 PCM -> 글자. 실패하면 {'ok': False, 'error': ...}"""
    if not start():
        return {"ok": False, "error": "음성 인식 엔진을 시작하지 못했습니다"}
    wav = Path(tempfile.gettempdir()) / ("ccv_voice_%s.wav" % uuid.uuid4().hex[:8])
    try:
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm16_bytes)
        b = "----ccv" + uuid.uuid4().hex
        body = b""
        for k, v in (("temperature", "0.0"), ("response_format", "json")):
            body += ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (b, k, v)).encode()
        body += ('--%s\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\nContent-Type: audio/wav\r\n\r\n' % b).encode()
        body += wav.read_bytes() + ("\r\n--%s--\r\n" % b).encode()
        req = urllib.request.Request("http://127.0.0.1:%d/inference" % _port, data=body,
                                     headers={"Content-Type": "multipart/form-data; boundary=" + b})
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read().decode("utf-8", "replace"))
        return {"ok": True, "text": _clean(out.get("text", ""))}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    finally:
        wav.unlink(missing_ok=True)
