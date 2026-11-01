# Claude Code 대화 뷰어

Claude Code로 나눈 대화(`~/.claude/projects/**/*.jsonl`)를 읽기 좋게 보고, HTML·TXT 문서로 저장하는 Windows 프로그램입니다.

**[다운로드 페이지](https://dh-chat-viewer.web.app/)** · [최신 exe 바로 받기](https://github.com/hydrangea111/claude-chat-viewer/releases/latest/download/ClaudeChatViewer.exe)

## 기능
- 내 PC의 Claude Code 대화를 자동으로 찾아 목록으로 표시, 검색
- 대화 / 파일 / 명령 / 기타로 나눠 보기
- HTML, TXT 저장, 브라우저로 보기
- 파일 주소 넣기: 파일을 고르거나 끌어다 놓으면 경로가 입력창에 들어감
- 입력창: 설치된 Claude Code로 대화에 이어서 말하기 (읽기만 / 파일 수정 / 모두 허용). 응답 중에도 입력하면 예약되어 끝난 뒤 자동 전송. 뷰어에서 한 대화도 터미널의 /resume 목록에 보임
- 대화 이름 바꾸기, 대화 삭제(휴지통으로 이동)
- 우클릭 복사·붙여넣기, 대화 글 드래그 복사와 메시지별 복사 버튼
- 대화를 열면 가장 최근 메시지부터 보임
- 밝은 화면 · 어두운 화면

변경 내역은 [CHANGELOG.md](CHANGELOG.md)를 보세요.

## 개인정보
대화를 읽고 저장하는 기능은 내 PC 안에서만 동작하며 어디로도 전송하지 않습니다.
입력창을 쓰면 PC에 설치된 Claude Code(`claude -p`)를 실행해 말을 전달하므로, 그 내용은 Claude Code가 평소처럼 Anthropic으로 전송합니다. 뷰어 자체에는 네트워크 접속 코드가 없습니다.

## 실행
- **exe:** Releases에서 받아 더블클릭. Windows "PC 보호" 경고가 뜨면 *추가 정보 → 실행*. (서명 없는 개인 프로그램)
- **소스(exe가 Windows에 막힐 때):** 소스를 받아 `run.bat`을 더블클릭하세요. 파이썬이 있는지, pywebview가 설치돼 있는지 확인하고 필요하면 설치를 안내합니다. 파이썬 설치부터 따라 하려면 [안내 페이지](https://dh-chat-viewer.web.app/python-install.html)를 보세요. 직접 하려면 `pip install pywebview` 후 `python chat_export.py`.
- 환경: Windows 10/11 64비트, Microsoft Edge WebView2 (Windows 11 기본 포함)
- 입력창을 쓰려면 Claude Code가 설치되고 로그인돼 있어야 합니다.

## 빌드
```
pip install pywebview pyinstaller pillow
python -m PyInstaller ClaudeChatViewer.spec
```
