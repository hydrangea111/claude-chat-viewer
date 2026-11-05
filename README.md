# Claude Code 대화 뷰어

Claude Code로 나눈 대화(`~/.claude/projects/**/*.jsonl`)를 읽기 좋게 보고, HTML·TXT 문서로 저장하는 Windows 10/11용 프로그램입니다.

**[다운로드 페이지](https://dh-chat-viewer.web.app/)** · [최신 exe 바로 받기](https://github.com/hydrangea111/claude-chat-viewer/releases/latest/download/ClaudeChatViewer.exe)

## 기능
- 내 PC의 Claude Code 대화를 자동으로 찾아 목록으로 표시, 검색
- 대화 / 파일 / 명령 / 기타로 나눠 보기
- HTML, TXT 저장, 브라우저로 보기
- 파일 주소 넣기: 파일을 고르거나 끌어다 놓으면 경로가 입력창에 들어감
- 입력창: 설치된 Claude Code로 대화에 이어서 말하기 (읽기만 / 파일 수정 / 모두 허용). 응답 중에도 입력하면 예약되어 끝난 뒤 자동 전송. 뷰어에서 한 대화도 터미널의 /resume 목록에 보임
- 대화 이름 바꾸기, 대화 삭제(휴지통으로 이동)
- 우클릭 복사·붙여넣기, 대화 글 드래그 복사, 메시지별 복사 버튼, 대화 전체 복사 버튼
- 대화를 열면 가장 최근 메시지부터 보이고, 파일·명령·기타 탭도 최근 항목이 위에 옴
- 선택 버튼(Claude가 고르게 하면 버튼으로 표시), 모델 선택, 단축어(/) 자동완성, 웹 검색·브라우저(Chrome) 연결 스위치, 토큰 사용량 표시
- 로그인이 풀리거나 인터넷이 끊기면 알림(로그인은 터미널에서 /login)
- 밝은 화면 · 어두운 화면

변경 내역은 [CHANGELOG.md](CHANGELOG.md)를 보십시오.

## 개인정보
대화를 읽고 저장하는 기능은 내 PC 안에서만 동작하며 어디로도 전송하지 않습니다.
도움말의 "문의하기"를 직접 눌러 보낸 경우에만, 적은 글·연락처(선택)·프로그램 버전·Windows 버전이 개발자의 서버(Firebase)로 전송됩니다. 대화 내용과 파일 경로는 보내지 않습니다. 음성 대화(🎙)를 처음 켤 때만, 음성 인식 프로그램(약 9MB)과 한국어 인식 모델(약 190MB)을 GitHub와 Hugging Face에서 내려받습니다. 내려받은 뒤에는 말 인식이 모두 내 PC 안에서 이루어져 음성이 밖으로 나가지 않으며, 음성 대화를 켜지 않으면 아무것도 받지 않습니다. 입력창을 쓰면 PC에 설치된 Claude Code(`claude -p`)를 실행해 말을 전달하므로, 그 내용은 Claude Code가 평소처럼 Anthropic으로 전송합니다. 뷰어는 연결·로그인 상태를 점검하려고 api.anthropic.com 에 접속만 해 보며(대화 내용은 보내지 않음) `claude auth status`를 읽기 전용으로 실행합니다. 웹 검색 스위치와 브라우저 연결 스위치는 기본이 꺼져 있고(브라우저는 켤 때마다 확인), 켜면 검색어나 화면 내용이 인터넷으로 나갈 수 있습니다. 시작할 때 새 버전이 있는지 보려고 다운로드 사이트의 작은 파일(`version.json`) 하나를 내려받으며, 보내는 정보는 없고 도움말에서 끌 수 있습니다.

## 실행
- **exe:** Releases에서 받아 더블클릭. Windows "PC 보호" 경고가 뜨면 *추가 정보 → 실행*. (서명 없는 개인 프로그램)
- **소스(exe가 Windows에 막힐 때):** 소스를 받아 `run.bat`을 더블클릭하십시오. 파이썬이 있는지, pywebview가 설치돼 있는지 확인하고 필요하면 설치를 안내합니다. 파이썬 설치부터 따라 하려면 [안내 페이지](https://dh-chat-viewer.web.app/python-install.html)를 보십시오. 직접 하려면 `pip install pywebview` 후 `python chat_export.py`.
- 환경: Windows 10/11 64비트, Microsoft Edge WebView2 (Windows 11 기본 포함)
- 입력창을 쓰려면 Claude Code가 설치되고 로그인돼 있어야 합니다.

## 빌드
```
pip install pywebview pyinstaller pillow
python -m PyInstaller ClaudeChatViewer.spec
```

## 라이선스

MIT 라이선스입니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 보십시오. 개인이 만든 비공식 도구이며 Anthropic과 관련이 없습니다.
