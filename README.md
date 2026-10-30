# Claude Code 대화 뷰어

Claude Code로 나눈 대화(`~/.claude/projects/**/*.jsonl`)를 읽기 좋게 보고, HTML·TXT 문서로 저장하는 Windows 프로그램입니다.

**[다운로드 페이지](https://dh-chat-viewer.web.app/)** · [최신 exe 바로 받기](https://github.com/hydrangea111/claude-chat-viewer/releases/latest/download/ClaudeChatViewer.exe)

## 기능
- 내 PC의 Claude Code 대화를 자동으로 찾아 목록으로 표시, 검색
- 대화 / 파일 / 명령 / 기타로 나눠 보기
- HTML, TXT 저장, 브라우저로 보기
- 밝은 화면 · 어두운 화면

## 개인정보
대화는 내 PC 안에서만 읽고 어디로도 전송하지 않습니다. 소스에 네트워크 접속 코드가 없습니다.

## 실행
- **exe:** Releases에서 받아 더블클릭. Windows "PC 보호" 경고가 뜨면 *추가 정보 → 실행*. (서명 없는 개인 프로그램)
- **소스:** `pip install pywebview` 후 `python chat_export.py` 또는 `run.bat`
- 환경: Windows 10/11 64비트, Microsoft Edge WebView2 (Windows 11 기본 포함)

## 빌드
```
pip install pywebview pyinstaller pillow
python -m PyInstaller ClaudeChatViewer.spec
```
