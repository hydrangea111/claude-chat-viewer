- **음성 대화**: 입력창 위의 **🎙 음성 대화**를 켜면 마이크로 말해서 대화합니다. 말을 마치고 잠시 쉬면 글자로 바꿔 보내고, **🔊 읽어 주기**를 켜면 Claude의 답을 Windows 한국어 음성으로 읽어 줍니다(코드와 주소는 읽지 않고, Esc로 멈춥니다).
- **인식은 내 PC 안에서 합니다**: 처음 켤 때 음성 인식 프로그램(whisper.cpp)과 한국어 모델(약 200MB)을 한 번만 내려받고, 받은 파일은 SHA-256을 확인한 뒤에만 씁니다. 음성은 PC 밖으로 나가지 않습니다.
- 말을 인식하면 바로 보낼지, 입력창에만 넣을지는 도움말의 "설정 안내"에서 고를 수 있습니다.
- **자동 안내 문구는 Claude Code 쪽으로 보입니다**: "Your response above was cut off…"처럼 Claude Code가 대신 끼워 넣는 안내와 `[Request interrupted by user]`는 내가 보낸 말풍선이 아니라 "시스템 안내" 줄로 접혀 보입니다. 내보내기에도 같은 방식으로 들어갑니다.


전체 변경 내역: [CHANGELOG.md](https://github.com/hydrangea111/claude-chat-viewer/blob/main/CHANGELOG.md)
