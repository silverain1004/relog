# Linux(WEB1) 배포 가이드 — 이중화 로그 분석

윈도우 버전(`win_analyzer.exe` + 작업 스케줄러)과 같은 일을 리눅스에서 하기 위한 가이드입니다.
**WEB1 서버 한 대에만 설치**하면 되고, WEB2/WAS1/WAS2에는 아무것도 설치하지 않습니다(SSH로 원격 수집).

```
[WEB1 10.20.30.11]  ← 여기에만 설치 (파이썬 3.6.8 + venv)
   ├─ 자기 자신의 nginx 로그: 직접 읽음
   ├─ WEB2 (10.20.30.12) ← SSH로 수집
   ├─ WAS1 (10.20.30.21) ← SSH로 수집
   └─ WAS2 (10.20.30.22) ← SSH로 수집
   → HTML 리포트 생성 → ZIP 메일 발송 (윈도우 버전과 동일한 방식)
```

---

## 0. 준비물

| 준비물 | 설명 |
|---|---|
| WEB1 접속 정보 | `appuser` 계정으로 SSH/터미널 접속 가능해야 함 (PuTTY 등) |
| `.ppk` 키 파일 | WEB2/WAS1/WAS2 접속용. 3단계에서 `.pem`으로 변환 |
| SMTP 정보 | 윈도우 버전 `config.json`의 `email` 부분 그대로 재사용 가능 |
| 파일 업로드 도구 | **WinSCP 권장** (PuTTY와 같은 키를 쓰는 GUI 복사 도구) |

---

## 1. 서버에 올릴 파일 (전체 프로젝트가 아님!)

레포 전체가 아니라 **`app/` 폴더의 파일 8개 + cron 견본 1개**만 올립니다.

**올릴 것** → 서버의 `/home/appuser/relog/` 폴더로:

| 파일 (레포 위치) | 역할 |
|---|---|
| `linux_analyzer.py` | 메인 프로그램 (윈도우의 `win_analyzer.exe`에 해당) |
| `cli_common.py` | 공통 모듈 (실행 옵션 처리) |
| `period_utils.py` | 공통 모듈 (주/월 기간 계산) |
| `report_builder.py` | 공통 모듈 (HTML 리포트 생성) |
| `mail_sender.py` | 공통 모듈 (ZIP + 메일 발송) |
| `ai_summary.py` | 공통 모듈 (Claude API로 AI 요약 생성) |
| `config.example.json` | 설정 견본 (서버에서 복사해 `config.json` 작성) |
| `requirements.txt` | 설치할 파이썬 패키지 목록 |
| `deploy/linux/crontab.example` | cron 등록용 견본 (4단계에서 사용) |

**올리지 말 것**: `app/win_analyzer.py`, `app/win_analyzer.spec`, `venv/`, `build/`, `dist/`, `reports/`, `__pycache__/`, 그리고 **`config.json`(비밀번호 포함이므로 서버에서 새로 작성)**

### 업로드 방법 (WinSCP 기준)

1. WinSCP 실행 → 호스트 `10.20.30.11`, 사용자 `appuser`, 기존 `.ppk` 키로 로그인
2. 오른쪽(서버)에서 `/home/appuser/` 이동 → 새 폴더 `relog` 생성
3. 왼쪽(내 PC)에서 `app/`의 위 8개 파일을 끌어다 놓기 (`crontab.example`은 같은 폴더에 둬도 무방)

명령줄이 편하면 내 PC에서 (PuTTY 설치 시 `pscp` 사용 가능):

```
cd C:\relog\app
pscp -i 내키.ppk linux_analyzer.py cli_common.py period_utils.py report_builder.py mail_sender.py ai_summary.py config.example.json requirements.txt appuser@10.20.30.11:/home/appuser/relog/
```

---

## 2. SSH 키 변환 (.ppk → .pem)

분석기(paramiko)는 PuTTY의 `.ppk`를 직접 읽지 못해서 **한 번만** OpenSSH 형식으로 변환합니다.

**방법 A — 내 PC에서 (권장, 쉬움)**

1. PuTTYgen 실행 → `Load`로 `.ppk` 열기
2. 메뉴 `Conversions` → `Export OpenSSH key` → `app_key.pem`으로 저장
3. WinSCP로 `/home/appuser/app_key.pem`에 업로드

**방법 B — WEB1 서버에서** (putty-tools가 설치돼 있을 때만)

```bash
puttygen ebiz.ppk -O private-openssh -o /home/appuser/app_key.pem
```

**변환 후 서버에서 반드시** (다른 사람이 못 읽게 — 이거 안 하면 SSH가 키를 거부함):

```bash
chmod 600 /home/appuser/app_key.pem
```

> `.ppk`/`.pem` 파일은 절대 git에 올리지 마세요 (`.gitignore`에 이미 등록돼 있음).

---

## 3. 파이썬 환경 만들기 (WEB1에서, 한 번만)

PuTTY로 WEB1에 접속한 뒤:

```bash
cd /home/appuser/relog

# venv = 이 프로그램 전용의 격리된 파이썬 (다른 프로그램에 영향 없음)
python3 -m venv venv

# 3.6용 마지막 pip로 업그레이드 (이걸 안 하면 패키지 설치가 실패할 수 있음)
venv/bin/pip install --upgrade "pip<22"

# paramiko(SSH 라이브러리) 설치
venv/bin/pip install -r requirements.txt

# 리포트/로그 폴더 준비
mkdir -p logs
```

설치 확인:

```bash
venv/bin/python -c "import paramiko; print(paramiko.__version__)"
```

버전 숫자(예: `2.12.0`)가 나오면 성공입니다.

---

## 4. config.json 작성 (WEB1에서)

```bash
cd /home/appuser/relog
cp config.example.json config.json
vi config.json        # 또는 nano config.json
```

고칠 곳은 두 군데입니다:

1. **`email` 블록** — 윈도우 버전 `config.json`의 값을 그대로 옮겨 적기 (SMTP 주소, 계정, 수신자)
2. **`linux` 블록** — IP는 이미 실서버 값이 들어 있으니, 확인만:
   - `key_path`: 2단계에서 올린 키 위치 (`/home/appuser/app_key.pem`)
   - `log_paths`: 실제 로그 위치와 다르면 수정 (아래 5-3 참고)
3. **`ai` 블록** — `api_key`에 Claude API 키 입력 (비우면 AI 요약만 건너뛰고 나머지는 정상 동작)
   - 키를 파일에 두기 싫으면 `api_key`를 비우고 환경변수 `ANTHROPIC_API_KEY`로 줘도 됨
   - 끄고 싶으면 `"enabled": false` 또는 실행 시 `--no-ai`

---

## 5. 사전 점검 3가지 (수동 실행 전에 꼭!)

### 5-1. 원격 서버 SSH 접속 확인

```bash
ssh -i /home/appuser/app_key.pem appuser@10.20.30.12 hostname   # WEB2
ssh -i /home/appuser/app_key.pem appuser@10.20.30.21 hostname   # WAS1
ssh -i /home/appuser/app_key.pem appuser@10.20.30.22 hostname   # WAS2
```

- 처음엔 `Are you sure you want to continue connecting (yes/no)?`가 나옴 → `yes`
- 각각 서버 이름이 출력되면 성공. **비밀번호를 물어보면 키 변환/권한(chmod 600)을 다시 확인**

### 5-2. 로그 읽기 권한 확인 (가장 자주 막히는 곳)

`/var/log/nginx/`는 보통 root 전용이라 `appuser`로는 안 읽힐 수 있습니다. 4대 모두 확인:

```bash
head -1 /var/log/nginx/access.log                                            # WEB1 (직접)
ssh -i /home/appuser/app_key.pem appuser@10.20.30.12 "head -1 /var/log/nginx/access.log"   # WEB2
ssh -i /home/appuser/app_key.pem appuser@10.20.30.21 "ls /usr/share/apache-tomcat-9.0.82/logs/ | head"  # WAS1
ssh -i /home/appuser/app_key.pem appuser@10.20.30.22 "ls /usr/share/apache-tomcat-9.0.82/logs/ | head"  # WAS2
```

`Permission denied`가 나오면 서버 관리자에게 요청:
> "`appuser` 계정이 nginx/tomcat 로그를 **읽기 전용**으로 볼 수 있게 해주세요 (adm 그룹 추가 또는 `setfacl -m u:appuser:rX /var/log/nginx` 등)"

### 5-3. 로그 파일 이름 확인 (참고용)

```bash
ls /var/log/nginx/
```

실서버는 일별 rotate + gzip 압축(`access.log-20260719.gz`) 방식으로 확인됐고,
**분석기가 자동으로 처리합니다** — 날짜별로 해당 날짜의 rotate/압축 파일까지 `zgrep`으로 함께 읽습니다.
config의 경로는 기본 파일(`/var/log/nginx/access.log`) 그대로 두면 됩니다.

> 참고: `error-besteel.log`(besteel 전용 로그)는 분석 대상에서 제외되어 있습니다. 필요하면 추후 추가 가능.

---

## 6. 수동 실행 (윈도우에서 exe 더블클릭에 해당)

먼저 **메일 없이** 리포트만:

```bash
cd /home/appuser/relog
venv/bin/python linux_analyzer.py --auto weekly --no-email
```

정상이면 이렇게 진행됩니다:

```
분석 기간: 2026년 29주 (2026-07-13 ~ 2026-07-19) (7일)
   [1/7] WEB1 - 2026-07-13 수집 중...
   ...
[1] L4 트래픽: WEB1(…) vs WEB2(…) | 편차 x.x% [정상]
[완료] HTML 리포트: /home/appuser/relog/reports/weekly/Report_EBIZ_2026W29.html
```

리포트를 내 PC로 내려받아(WinSCP) 브라우저로 열어 내용을 확인하세요.
숫자가 그럴듯하면 **메일 포함**으로 한 번 더:

```bash
venv/bin/python linux_analyzer.py --auto weekly
```

메일이 잘 오면 3단계 끝. 이후 `deploy/linux/crontab.example`을 보고 cron을 등록하면(4단계) 윈도우의 작업 스케줄러처럼 매주/매월 자동 실행됩니다.

---

## 7. 자주 나는 문제

| 증상 | 원인 / 해결 |
|---|---|
| `pip install` 실패, 빨간 에러 잔뜩 | pip가 너무 오래됨 → `venv/bin/pip install --upgrade "pip<22"` 먼저 |
| SSH가 비밀번호를 물어봄 | 키 변환이 안 됐거나 `chmod 600` 누락 |
| `Permission denied` (로그 읽기) | 5-2 참고 — 관리자에게 읽기 권한 요청 |
| 특정 노드만 `[수집 실패]`로 표기됨 | 그 서버만 SSH 불가(방화벽/키). 리포트는 나머지 노드로 정상 생성됨 |
| 리포트 숫자가 0에 가까움 | 서버에 `zgrep`이 있는지 확인(`which zgrep`) — 없으면 gzip 패키지 설치 필요 |
| cron으로 돌릴 때만 한글이 깨짐/죽음 | crontab 맨 위에 `PYTHONIOENCODING=utf-8` 한 줄 추가 (예시 파일에 포함됨) |
| `[AI 요약] 호출 실패 (... timed out / Connection refused)` | WEB1에서 외부 인터넷이 막힘 → `curl -I https://api.anthropic.com` 로 확인. 프록시가 있으면 crontab에 `HTTPS_PROXY=` 추가, 없으면 `ai.enabled`를 false로 |
| `[AI 요약] 호출 실패 (CERTIFICATE_VERIFY_FAILED)` | 서버 CA 인증서가 오래됨 → `sudo yum update ca-certificates` (관리자 요청) |
| `[AI 요약] API 오류 401` | API 키 오타/만료 — `config.json`의 `ai.api_key` 확인 |
| `config.json에 'linux' 섹션이 없습니다` | `config.example.json`을 복사하지 않고 옛 설정을 재사용한 경우 |
