# quincy-mascot

퀸시 마스코트의 **자동 업데이트 페이로드**입니다. 사람이 읽을 것은 없습니다.

앱이 시작할 때 `version.json` 을 받아 파일별 SHA-256을 대조하고, 바뀐 파일만
`raw.githubusercontent.com` 에서 내려받아 아래 위치에 넣습니다.

```
~/Library/Application Support/QuincyMascot/live/
```

- 전부 성공했을 때만 통째로 교체합니다. 도중에 끊겨도 새 이미지와 옛 배치 파일이
  섞인 상태가 되지 않습니다.
- 오프라인이거나 실패하면 조용히 앱에 들어 있는 원본으로 실행합니다.
- 설정과 타이머 기록은 업데이트와 무관하게 유지됩니다.

`.gitattributes` 의 `* -text` 는 지우면 안 됩니다. git이 줄바꿈을 바꾸면 받은
바이트가 달라져 해시가 영원히 어긋나고, 그 파일에서 업데이트가 멈춥니다.

원본은 [ena-workspace](https://github.com/rlfqjxm0-create/ena-workspace) 의
`ena-mascot/` 에 있고, `make_manifest.py` 가 이 레포로 밀어 넣습니다.
