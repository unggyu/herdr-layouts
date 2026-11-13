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
- 선택적으로 Codex 대화 자동 재개 설정

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

### Codex 대화 자동 재개

압축 해제한 패키지 폴더의 명령 프롬프트에서 실행합니다.

```bat
install.cmd --enable-session-recovery
```

별도의 core `shell` 설정이 없을 때 복구 셸을 등록합니다. 기존 `shell` 설정이 있으면 보존하고 자동 설정을 건너뜁니다. 설정은 다음 core 시작부터 적용되며, 설치 프로그램이 실행 중인 코어·터미널을 종료하지는 않습니다.

이 기능은 저장된 메타데이터를 이용해 Codex 대화를 재개합니다. 종료된 프로세스 자체를 복원하는 기능은 아닙니다.

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
