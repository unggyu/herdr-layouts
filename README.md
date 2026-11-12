# Herdr custom layouts

Windows x64 + WSL용 Herdr 커스텀 레이아웃입니다. 두 브랜치에서 각각 관리합니다.

| 브랜치 | 레이아웃 | 설명 |
|---|---|---|
| `terminals` | `tabs` | Terminals 기반 탭 UI |
| `herdr-98` | `win98-plus` | Windows 98 바탕화면·작업 표시줄 UI |

## 다른 PC에 설치

Herdr Windows 앱과 WSL을 먼저 설치하고 Herdr를 한 번 실행하세요.
생성된 설치 ZIP 전체를 압축 해제하고 **`install.cmd`**를 실행한 뒤, 설정 → Look에서 해당 레이아웃을 선택합니다.
Python 실행 도구와 필요한 모드·폰트·이미지가 ZIP에 포함되므로 Windows Python을 따로 설치할 필요는 없습니다.

기존 키 설정은 병합하고 덮어쓰는 파일은 Herdr 홈의 `backups/레이아웃-날짜/`에 보관합니다. 현재 PC의 열린 탭·대화·세션 기록·SSH 키·인증정보·모바일 릴레이 설정은 가져오지 않습니다.

## 빌드

저장소의 Python 소스를 실행할 수 있는 환경에서 브랜치를 고른 뒤 빌드합니다. WSL에서는 시스템 Python 3를 사용하면 됩니다.

```bash
git switch terminals      # 또는 git switch herdr-98
python3 -m unittest discover -s tests
python3 build.py
```

Windows Python으로 빌드한다면 `python3` 대신 `py -3`를 사용하세요.
결과는 `dist/`에 ZIP과 SHA256 파일로 생성됩니다. 첫 빌드는 python.org에서 버전과 SHA256이 고정된 Windows embedded Python을 내려받습니다. `.cache/`와 `build/`, `dist/`는 Git에서 제외합니다.

기존 embedded Python이 있으면 오프라인 빌드도 가능합니다.

```bash
python3 build.py --runtime-dir /path/to/windows-embedded-python
```

## 기능과 사용법

- 탭 드래그 및 `Ctrl+Shift+Alt+←/→`로 탭 순서 이동
- 경로를 드래그로 선택 → 우클릭 → **기본 앱으로 열기** 또는 **파일 탐색기에서 보기**
- 우클릭 메뉴의 터미널 ID 복사
- `Ctrl+V` / `Ctrl+Shift+V` 이미지 붙여넣기
- `Ctrl+Shift+F12` 선택 파일을 탐색기에서 보기
- `Ctrl+Shift+Y` 동기 입력 패널
- 새 PC의 pane 메타데이터를 자체적으로 수집하는 세션 복구 서비스

WSL 파일 경로 연결에는 WSL의 `/usr/bin/python3`가 필요하며, 복구 서비스가 해당 pane의 WSL 배포판을 확인해야 합니다. 원격 SSH 서버의 파일은 로컬 WSL 파일과 별개입니다. 경로를 직접 클릭하는 기본 링크 동작은 이 커스텀 메뉴와 다릅니다.

재시작 후 Codex 자동 재개를 쓰려면 `install.cmd --enable-session-recovery`를 실행하세요. 별도 core shell 설정이 없을 때만 복구 셸을 추가합니다. 기존 shell 설정은 보존하며, 변경은 다음 core 시작부터 적용됩니다. 실행 중인 코어·터미널을 설치 프로그램이 종료하지 않습니다.

## 수정과 배포

`payload/`가 Git으로 관리하는 원본입니다. Herdr 실행 폴더를 바꿨다면 원하는 변경만 여기에 반영하고 다시 빌드하세요. 실행 중인 설정 폴더가 저장소로 자동 동기화되지는 않습니다.

`profile.json`은 현재 브랜치의 레이아웃과 검사할 모드 목록, `keys.patch.json`은 가져올 키 바인딩입니다. `__HERDR_PYTHON__` 등의 경로 토큰은 설치 때 해당 PC 경로로 바뀝니다. 공통 기능을 수정할 때는 다른 브랜치에도 같은 커밋을 cherry-pick하거나 필요한 변경을 반영하세요.

Orchestration 스킬과 모바일 릴레이는 레이아웃과 별개이므로 포함하지 않습니다. 출처와 라이선스는 [NOTICE.md](NOTICE.md)를 참고하세요.
