# Herdr Custom Layouts

Windows x64와 WSL 환경에서 사용하는 [Herdr](https://github.com/herdrdev/herdr-app) 커스텀 레이아웃입니다. Terminals와 Windows 98 스타일의 UI에 탭 이동, WSL 이미지 붙여넣기, 파일 열기, 터미널 ID 복사 기능을 추가합니다.

## 레이아웃

각 레이아웃은 별도 브랜치에서 관리합니다. 필요한 브랜치를 선택해 빌드하세요.

| 브랜치 | Herdr에서 표시되는 이름 | 구성 | 설치 패키지 |
|---|---|---|---|
| [`terminals`](https://github.com/unggyu/herdr-layouts/tree/terminals) | `tabs` | 상단 탭 바와 터미널 pane | `Herdr-Terminals-Custom.zip` |
| [`herdr-98`](https://github.com/unggyu/herdr-layouts/tree/herdr-98) | `win98-plus` | Windows 98 바탕화면, 작업 표시줄, 창 제목 표시줄 | `Herdr-98-Custom.zip` |

## 주요 기능

- 탭을 드래그하거나 단축키로 순서 이동
- 선택한 파일 경로를 Windows 기본 앱으로 열거나 탐색기에서 표시
- `/home/...`, `~/...`, `/mnt/c/...` 등 WSL 경로를 Windows 경로로 변환
- 우클릭 메뉴에서 터미널 ID 확인 및 복사
- Windows 클립보드의 이미지를 WSL 터미널에 붙여넣기
- 여러 터미널에 같은 입력을 보내는 동기 입력 패널
- pane별 대화 이력 저장 및 선택한 Codex 대화 수동 재개

Windows 98 버전에는 UI에 필요한 폰트·아이콘·소리가 포함됩니다.

## 요구 사항

- Windows x64에 설치된 Herdr 데스크톱 앱과 herdr-core
- WSL 연동 기능을 사용할 경우 WSL 배포판과 배포판 내부의 `/usr/bin/python3`
- 소스에서 빌드할 경우 Python 3.11 이상과 Git

설치 전에 Herdr를 한 번 실행하세요. 설치 프로그램은 기본 설치 경로인 `%LOCALAPPDATA%\Programs\herdr-app\herdr-app.exe`를 사용합니다.

## 설치

### 1. 소스 받기

```bash
git clone https://github.com/unggyu/herdr-layouts.git
cd herdr-layouts
git switch herdr-98
```

Terminals 버전을 사용하려면 마지막 명령을 `git switch terminals`로 바꾸세요.

### 2. 설치 패키지 만들기

WSL 또는 Linux에서:

```bash
python3 -m unittest discover -s tests
python3 build.py
```

Windows에서:

```powershell
py -3 -m unittest discover -s tests
py -3 build.py
```

결과는 `dist/`에 ZIP과 SHA256 파일로 생성됩니다. 첫 빌드는 python.org에서 `runtime.lock.json`에 지정된 Windows embedded Python을 내려받고 SHA256을 검증합니다. 다운로드에는 인터넷 연결이 필요합니다.

### 3. Herdr에 적용

1. 생성된 ZIP **전체를 압축 해제**합니다.
2. 압축 해제한 폴더에서 `install.cmd`를 실행합니다.
3. Herdr 설정 → **Look**에서 `tabs` 또는 `win98-plus`를 선택합니다. Herdr가 실행 중이면 설치 프로그램이 레이아웃 전환을 시도합니다.

패키지에는 Python 실행 도구가 포함됩니다. 이미 빌드된 패키지를 설치할 때는 별도의 Windows Python 설치가 필요하지 않습니다.

기존 키 설정은 병합되며, 같은 단축키는 이 프로젝트의 바인딩으로 변경됩니다. 덮어쓰는 파일은 Herdr 설정 폴더의 `backups/<레이아웃>-<날짜>/`에 보관합니다. 개인 세션 기록, 대화, SSH 키, 인증정보는 패키지에 포함되지 않습니다.

## 사용법

| 기능 | 조작 |
|---|---|
| 탭 순서 이동 | 탭 드래그 또는 `Ctrl+Shift+Alt+←/→` |
| 기본 앱으로 파일 열기 | 경로 드래그 선택 → 우클릭 → **기본 앱으로 열기** |
| 탐색기에서 파일 표시 | 경로 드래그 선택 → 우클릭 → **파일 탐색기에서 보기**, 또는 `Ctrl+Shift+F12` |
| 터미널 ID 복사 | 우클릭 → **터미널 ID 복사** |
| 이미지 붙여넣기 | `Ctrl+V` 또는 `Ctrl+Shift+V` |
| 동기 입력 패널 | `Ctrl+Shift+Y` |

파일 열기 기능은 **선택한 텍스트**를 사용합니다. 경로를 직접 클릭하는 Herdr 기본 링크 동작과는 별개입니다. 선택에 포함된 닫는 괄호나 터미널 줄바꿈도 처리합니다.

WSL 경로를 열려면 메타데이터 수집 서비스가 해당 pane의 배포판과 Linux 작업 경로를 확인해야 합니다. 원격 SSH 서버의 경로는 로컬 WSL 파일 경로로 취급하지 마세요.

### Codex 대화 복구

이 버전은 자동 실행 대신 `Ctrl+Shift+R`의 목록에서 선택해 복구합니다. 기존 `--enable-session-recovery` 옵션은 호환성을 위해 남아 있으나, 복구 셸이 시작되어도 대화를 자동 재개하지 않습니다. 자세한 사용법은 아래 **Pane 대화 이력과 수동 복구**를 참고하세요.

## 개발

`payload/`가 레이아웃과 모드의 원본입니다. 소스를 수정한 뒤 테스트와 빌드를 실행하고 생성된 패키지를 설치해 적용합니다. Herdr 실행 폴더에서 직접 수정한 파일은 저장소에 자동 반영되지 않습니다.

| 경로 | 용도 |
|---|---|
| `payload/layouts/` | 레이아웃 정의와 미리보기 |
| `payload/mods/` | 커스텀 UI와 클립보드·파일·복구 기능 |
| `payload/themes/` | 테마 정의 — Windows 98 브랜치 |
| `profile.json` | 브랜치의 레이아웃, 패키지 이름, 검사할 모드 목록 |
| `keys.patch.json` | 설치 시 병합할 키 바인딩 |
| `build.py` | 설치 ZIP 생성 |
| `install.py`, `install.cmd` | Windows 설치 프로그램 |
| `runtime.lock.json` | 빌드에 사용할 Python 버전과 SHA256 |
| `tests/` | 경로 처리 회귀 테스트 |

`__HERDR_PYTHON__` 등의 경로 토큰은 설치 시 대상 환경의 경로로 치환됩니다. `.cache/`, `build/`, `dist/`와 세션 데이터는 Git에서 제외합니다. 공통 모드 변경은 두 브랜치에 반영하세요.

기존 Windows embedded Python 폴더를 사용하면 런타임 다운로드 없이 빌드할 수 있습니다.

```bash
python3 build.py --runtime-dir /path/to/windows-embedded-python
```

## 범위와 라이선스

이 저장소는 레이아웃과 관련 모드를 제공합니다. 별도로 설치하는 orchestration 스킬이나 모바일 릴레이는 포함하지 않습니다.

코드와 포함된 자산의 출처 및 라이선스는 [NOTICE.md](NOTICE.md)와 [LICENSE](LICENSE)를 참고하세요.

## Pane 대화 이력과 수동 복구

`win98-plus`와 `tabs`에서 `Ctrl+Shift+R`을 누르거나 pane을 우클릭한 뒤, **기본 앱으로 열기** 바로 아래의 **대화 이력·복구**를 선택합니다. 제목·폴더·대화 ID를 Windows에 보관하므로 WSL이 꺼져 있어도 확인할 수 있습니다. 각 pane의 이전 기록을 펼치거나 여러 항목을 선택해 재개할 수 있습니다.

복구는 항상 `codex --yolo resume <ID>`로 실행합니다. 모델·프로필은 유지하고 충돌하는 승인·샌드박스 옵션은 제외합니다. 입력 없는 PowerShell pane에서만 복구하며, 실행 중인 대화는 중복으로 열지 않습니다. ID 미확인 항목은 **같은 폴더 대화 찾기**로 후보를 조회한 뒤 선택하세요. 후보 조회·복구 버튼은 WSL을 시작할 수 있습니다. 이력 조회 자체는 WSL을 시작하지 않습니다.

기록은 `<Herdr home>/mods/session-restore/data/history.sqlite`에 pane당 최근 100건을 저장합니다. 자동 복구와 시작 시 WSL 깨우기는 사용하지 않습니다. 명령 전달 후 실제 대화가 확인되지 않으면 실패로 표시하므로 pane 화면을 확인하세요. 새 기능 적용 이전의 제목 변화는 복원할 수 없으며, 기존 최신 기록부터 이력을 시작합니다.
