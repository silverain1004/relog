"""GitHub Pages용 데모 리포트 생성기.

실서버 로그 대신 '가짜(합성) 로그'를 만들어서, 운영 중인 분석 코드
(win_analyzer / linux_analyzer / report_builder / ai_summary)를 그대로 돌린다.
결과물은 docs/demo/ 아래에 정적 HTML로 떨어지고, GitHub Pages가 그대로 서빙한다.

    python demo/generate_demo.py              # 저장된 AI 요약(캐시) 사용
    ANTHROPIC_API_KEY=sk-... python demo/generate_demo.py --refresh-ai   # Claude로 새로 요약

샘플 로그의 IP는 문서용 대역(RFC 5737: 192.0.2.x, 198.51.100.x, 203.0.113.x)과
사설 대역(10.20.30.x)만 쓴다. 실서버 로그는 한 줄도 들어 있지 않다.
"""
import argparse
import json
import os
import random
import shutil
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import linux_analyzer  # noqa: E402
import win_analyzer  # noqa: E402
from ai_summary import build_linux_digest, build_win_digest, generate_ai_summary  # noqa: E402
from period_utils import resolve_auto_period  # noqa: E402
from report_builder import build_linux_email_html, build_win_email_html  # noqa: E402

DEMO_DIR = os.path.join(ROOT, "demo")
SAMPLE_DIR = os.path.join(DEMO_DIR, "sample_logs")
DOCS_DIR = os.path.join(ROOT, "docs", "demo")
CACHE_PATH = os.path.join(DEMO_DIR, "ai_summary_cache.json")

PERIOD = resolve_auto_period("weekly", date(2026, 11, 2))  # 2026-W44 (10/26 ~ 11/01)
INCIDENT_DAY = date(2026, 10, 29)  # 데모 시나리오: 이 날 오후 DB 커넥션 풀 고갈

MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SAFE_BYTES = [512, 768, 1288, 2361, 3172, 5520, 8192, 1536]  # 상태코드 키워드(401/403/404/500)와 안 겹치는 크기

NORMAL_URLS = [
    "/", "/main", "/api/orders", "/api/orders/list?page=1", "/api/notice", "/api/products/search?q=coil",
    "/static/js/app.js", "/static/css/app.css", "/api/dashboard/summary", "/api/inventory/stock",
]
SCAN_URLS = [
    ("/wp-login.php", "404"), ("/xmlrpc.php", "404"), ("/.env", "404"), ("/.git/config", "404"),
    ("/phpmyadmin/index.php", "404"), ("/admin", "403"), ("/cgi-bin/luci;stok=/locale", "404"),
    ("/remote/logincheck", "404"), ("/backup.bak", "404"), ("/etc/passwd", "400"),
]
SCANNER_IPS = ["203.0.113.45", "203.0.113.77", "198.51.100.23", "198.51.100.180", "192.0.2.66"]
USER_IPS = ["10.20.40.%d" % i for i in range(11, 60)]


# ------------------------------------------------------------------
# 1. 합성 로그 생성
# ------------------------------------------------------------------
def _nginx_ts(d, h, rnd):
    return "%02d/%s/%d:%02d:%02d:%02d +0900" % (d.day, MON[d.month - 1], d.year, h, rnd.randint(0, 59), rnd.randint(0, 59))


def _access(ip, ts, method, url, status, ua="Mozilla/5.0", rnd=None):
    size = rnd.choice(SAFE_BYTES)
    return '%s - - [%s] "%s %s HTTP/1.1" %s %d "-" "%s"' % (ip, ts, method, url, status, size, ua)


def _tomcat_ts(d, h, rnd):
    return "%02d-%s-%d %02d:%02d:%02d.%03d" % (
        d.day, MON[d.month - 1], d.year, h, rnd.randint(0, 59), rnd.randint(0, 59), rnd.randint(0, 999))


def write_sample_logs(rnd):
    if os.path.exists(SAMPLE_DIR):
        shutil.rmtree(SAMPLE_DIR)
    nginx_dir = os.path.join(SAMPLE_DIR, "nginx")
    eout_dir = os.path.join(SAMPLE_DIR, "tomcat-eout")
    inout_dir = os.path.join(SAMPLE_DIR, "tomcat-inout")
    for p in (nginx_dir, eout_dir, inout_dir):
        os.makedirs(p)

    days = [PERIOD["start"] + timedelta(days=i) for i in range(7)]
    access, error = [], []
    for d in days:
        weekend = d.weekday() >= 5
        for _ in range(250 if weekend else 1400):  # 정상 트래픽 (키워드 미매치 → 집계 제외)
            h = rnd.choice(range(8, 19)) if not weekend else rnd.randint(0, 23)
            access.append(_access(rnd.choice(USER_IPS), _nginx_ts(d, h, rnd), "GET", rnd.choice(NORMAL_URLS), "200", rnd=rnd))
        for _ in range(96):  # 업타임 체크 (exclude 대상)
            access.append(_access("35.191.0.%d" % rnd.randint(1, 250), _nginx_ts(d, rnd.randint(0, 23), rnd), "GET", "/", "200",
                                  ua="GoogleStackdriverMonitoring-UptimeChecks(https://cloud.google.com/monitoring)", rnd=rnd))
        for _ in range(rnd.randint(30, 60) if not weekend else 8):  # 토큰 만료 재발급 401 (노이즈)
            access.append(_access(rnd.choice(USER_IPS), _nginx_ts(d, rnd.randint(8, 19), rnd), "GET",
                                  "/api/proxy/users/refresh-token", "401", rnd=rnd))
        for _ in range(rnd.randint(25, 70)):  # 인터넷 스캐너
            url, st = rnd.choice(SCAN_URLS)
            access.append(_access(rnd.choice(SCANNER_IPS), _nginx_ts(d, rnd.randint(0, 23), rnd), "GET", url, st,
                                  ua="Mozilla/5.0 zgrab/0.x", rnd=rnd))
        for _ in range(rnd.randint(3, 8)):  # 로그인 실패
            access.append(_access(rnd.choice(USER_IPS), _nginx_ts(d, rnd.randint(8, 19), rnd), "POST", "/api/login", "401", rnd=rnd))
        if d == INCIDENT_DAY:  # 14~15시 주문 API 500 폭증
            for _ in range(180):
                access.append(_access(rnd.choice(USER_IPS), _nginx_ts(d, rnd.choice([14, 14, 14, 15]), rnd), "POST",
                                      "/api/orders/submit", "500", rnd=rnd))
            for _ in range(40):
                error.append('%s [error] 2211#0: *%d upstream timed out (110: Connection timed out) while reading response '
                             'header from upstream, client: %s, server: _, request: "POST /api/orders/submit HTTP/1.1", '
                             'upstream: "http://127.0.0.1:8080/api/orders/submit"' % (
                                 d.strftime("%Y/%m/%d") + " 14:%02d:%02d" % (rnd.randint(0, 59), rnd.randint(0, 59)),
                                 rnd.randint(10000, 99999), rnd.choice(USER_IPS)))
        else:
            for _ in range(rnd.randint(0, 2)):
                access.append(_access(rnd.choice(USER_IPS), _nginx_ts(d, rnd.randint(8, 19), rnd), "GET", "/api/orders/export", "500", rnd=rnd))
    access.sort(key=lambda ln: ln.split("[", 1)[1][:20])
    _write(os.path.join(nginx_dir, "access.log"), access)
    _write(os.path.join(nginx_dir, "error.log"), error)

    for d in days:
        eout, inout = [], []
        for h in range(0, 24, 3):
            eout.append("%s INFO [main] org.apache.catalina.core.StandardServer heartbeat ok" % _tomcat_ts(d, h, rnd))
            inout.append("%s INFO [main] org.apache.catalina.core.StandardServer heartbeat ok" % _tomcat_ts(d, h, rnd))
        for _ in range(rnd.randint(1, 4)):  # HTTP 포트로 들어온 TLS 핸드셰이크 (스캐너)
            inout.append("%s INFO [http-nio-8080-exec-%d] org.apache.coyote.http11.Http11Processor.service Error parsing HTTP "
                         "request header java.lang.IllegalArgumentException: Invalid character found in method name. "
                         "HTTP method names must be tokens" % (_tomcat_ts(d, rnd.randint(0, 23), rnd), rnd.randint(1, 20)))
        if d == INCIDENT_DAY:
            for _ in range(60):
                eout.append("%s SEVERE [http-nio-8080-exec-%d] com.example.order.OrderService.submit "
                            "java.sql.SQLTransientConnectionException: HikariPool-1 - Connection is not available, "
                            "request timed out after 30000ms." % (_tomcat_ts(d, rnd.choice([14, 14, 15]), rnd), rnd.randint(1, 50)))
            for _ in range(12):
                eout.append("%s WARNING [HikariPool-1 housekeeper] com.zaxxer.hikari.pool.HikariPool - HikariPool-1 - "
                            "Thread starvation or clock leap detected" % _tomcat_ts(d, 14, rnd))
        for _ in range(rnd.randint(0, 2)):
            eout.append("%s WARNING [http-nio-8080-exec-%d] o.a.c.c.C.[.[localhost] login fail: unauthorized access "
                        "(invalid password)" % (_tomcat_ts(d, rnd.randint(8, 19), rnd), rnd.randint(1, 50)))
        eout.sort()
        inout.sort()
        _write(os.path.join(eout_dir, "catalina.%s.log" % d.isoformat()), eout)
        _write(os.path.join(inout_dir, "catalina.%s.log" % d.isoformat()), inout)
    return nginx_dir, eout_dir, inout_dir


def _write(path, lines):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


# ------------------------------------------------------------------
# 2. Linux: SSH/zgrep 대신 합성 데이터를 넣는 분석기
# ------------------------------------------------------------------
LINUX_SERVERS = [
    {"name": "WEB1", "ip": "10.20.30.11", "role": "WEB", "is_local": True},
    {"name": "WEB2", "ip": "10.20.30.12", "role": "WEB", "is_local": False},
    {"name": "WAS1", "ip": "10.20.30.21", "role": "WAS", "is_local": False},
    {"name": "WAS2", "ip": "10.20.30.22", "role": "WAS", "is_local": False},
]


class DemoLinuxAnalyzer(linux_analyzer.LinuxMasterAnalyzer):
    """_run_cmd(SSH 실행)만 합성 결과로 바꾼다. 집계·분류·리포트 코드는 운영 코드 그대로."""

    def __init__(self, period, rnd):
        cfg = {"ssh_user": "demo", "key_path": "-", "servers": LINUX_SERVERS, "log_paths": {
            "WEB": {"access": "/var/log/nginx/access.log", "error": "/var/log/nginx/error.log"},
            "WAS": {"catalina": "catalina.{}.log", "ebiz": "ebiz.log.{}"}}}
        super().__init__(period, cfg)
        self.rnd = rnd
        self._day = None

    def _fetch_day(self, server, day, day_idx, total_days):
        self._day = day
        return super()._fetch_day(server, day, day_idx, total_days)

    def _run_cmd(self, server, cmd):
        rnd, d, name = self.rnd, self._day, server["name"]
        weekend = d.weekday() >= 5
        if "wc -l" in cmd or "grep -c" in cmd:  # 트래픽 건수
            base = {"WEB1": 41000, "WEB2": 39500, "WAS1": 23000, "WAS2": 22500}[name]
            return str(int(base * (0.35 if weekend else 1.0) * rnd.uniform(0.92, 1.08)))
        lines = []
        stamp = d.strftime("%Y/%m/%d")
        if server["role"] == "WEB":
            pool = [
                ('open() "/usr/share/nginx/html/remote/logincheck" failed (2: No such file or directory)', "/remote/logincheck"),
                ('open() "/usr/share/nginx/html/wp-login.php" failed (2: No such file or directory)', "/wp-login.php"),
                ('open() "/usr/share/nginx/html/.env" failed (2: No such file or directory)', "/.env"),
                ('open() "/usr/share/nginx/html/.git/config" failed (2: No such file or directory)', "/.git/config"),
                ('open() "/usr/share/nginx/html/xmlrpc.php" failed (2: No such file or directory)', "/xmlrpc.php"),
            ]
            for _ in range(rnd.randint(40, 120)):
                msg, url = rnd.choice(pool)
                lines.append('%s %02d:%02d:%02d [error] 1873#0: *%d %s, client: %s, server: _, request: "GET %s HTTP/1.1"' % (
                    stamp, rnd.randint(0, 23), rnd.randint(0, 59), rnd.randint(0, 59), rnd.randint(1000, 99999),
                    msg, rnd.choice(SCANNER_IPS), url))
            if name == "WEB2" and d == INCIDENT_DAY:
                for _ in range(9):
                    lines.append('%s 14:%02d:%02d [error] 1873#0: *%d upstream prematurely closed connection while reading '
                                 'response header from upstream, client: 10.20.40.%d, request: "POST /api/approval HTTP/1.1"' % (
                                     stamp, rnd.randint(0, 59), rnd.randint(0, 59), rnd.randint(1000, 99999), rnd.randint(11, 59)))
        else:
            ts = "%02d-%s-%d" % (d.day, MON[d.month - 1], d.year)
            for _ in range(rnd.randint(2, 6)):
                lines.append("%s %02d:%02d:%02d.000 WARNING [http-nio-8080-exec-3] o.a.c.util.SessionIdGeneratorBase "
                             "Creation of SecureRandom instance took [%d] ms" % (ts, rnd.randint(0, 23), rnd.randint(0, 59),
                                                                               rnd.randint(0, 59), rnd.randint(200, 900)))
            if name == "WAS1" and d == INCIDENT_DAY:
                for _ in range(6):
                    lines.append("%s 14:%02d:%02d.000 SEVERE [http-nio-8080-exec-17] c.e.approval.ApprovalController "
                                 "java.net.SocketTimeoutException: Read timed out (mail gateway)" % (
                                     ts, rnd.randint(0, 59), rnd.randint(0, 59)))
        return "\n".join(lines)

    def close_ssh_clients(self):
        pass


# ------------------------------------------------------------------
# 3. AI 요약 (캐시)
# ------------------------------------------------------------------
FALLBACK_AI = {
    "windows": [
        "종합: 주의 — 10/29(목) 14시대 주문 API 500 오류가 몰렸고, 같은 시각 DB 커넥션 풀 고갈 로그가 있습니다.",
        "TOMCAT_EOUT: 10/29 14~15시 HikariPool 'Connection is not available' 60건 — 커넥션 풀 크기·슬로우 쿼리 점검 권장",
        "NGINX: POST /api/orders/submit 500 180건과 upstream timed out 40건이 같은 시간대에 발생, 위 DB 이슈의 영향으로 보임",
        "wp-login·.env·.git 등 스캔성 404와 refresh-token 401은 인터넷 배경 노이즈로 조치 불필요",
    ],
    "linux": [
        "종합: 정상 — L4 편차는 임계치(15%) 이내이며, 노이즈 대부분은 알려진 스캔 시그니처입니다.",
        "WEB2: 10/29 14시 upstream prematurely closed 9건(미분류) — 결재 API 응답 지연 여부 확인 권장",
        "WAS1: 같은 시각 메일 게이트웨이 SocketTimeoutException 6건 — WEB2 미분류 건과 연관 가능성",
        "FortiOS·WordPress·정찰성 스캔은 404로 차단되어 조치 불필요",
    ],
}


def resolve_ai(kind, digest, refresh):
    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)
    if refresh:
        lines = generate_ai_summary({"enabled": True, "model": os.environ.get("AI_MODEL", "claude-haiku-4-5")}, digest)
        if lines:
            cache[kind] = {"source": "claude", "lines": lines}
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
    entry = cache.get(kind) or {"source": "example", "lines": FALLBACK_AI[kind]}
    return entry["lines"], entry["source"]


# ------------------------------------------------------------------
# 4. 실행
# ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh-ai", action="store_true", help="ANTHROPIC_API_KEY로 Claude 요약을 새로 받아 캐시에 저장")
    args = ap.parse_args()

    rnd = random.Random(20261029)
    nginx_dir, eout_dir, inout_dir = write_sample_logs(rnd)
    reports_dir = os.path.join(DOCS_DIR, "reports")
    email_dir = os.path.join(DOCS_DIR, "email")
    os.makedirs(email_dir, exist_ok=True)

    # --- Windows: 운영 코드의 LOG_CONFIG 경로만 샘플 폴더로 교체
    win_analyzer.LOG_CONFIG["NGINX"]["path"] = nginx_dir
    win_analyzer.LOG_CONFIG["TOMCAT_EOUT"]["path"] = eout_dir
    win_analyzer.LOG_CONFIG["TOMCAT_INOUT"]["path"] = inout_dir
    wa = win_analyzer.WindowsLogAnalyzer(PERIOD)
    wa.output_dir = reports_dir
    os.makedirs(reports_dir, exist_ok=True)
    win = wa.run(ai_cfg=None)  # 요약은 아래에서 캐시/실호출로 넣는다

    systems = []
    # run()은 systems_data를 밖으로 안 돌려주므로 한 번 더 파싱 (리포트 파일은 같은 내용으로 덮어씀)
    for sys_name, cfg in win_analyzer.LOG_CONFIG.items():
        data = wa.parse_logs(sys_name, cfg)
        if data:
            systems.append((sys_name, data))
    win_ai, win_src = resolve_ai("windows", build_win_digest(PERIOD["label"], systems), args.refresh_ai)
    win_summary = ["- [AI] " + ln for ln in win_ai] + [""] + [ln for ln in win["summary_lines"]]
    _save(os.path.join(email_dir, "windows.html"), build_win_email_html(PERIOD["label"], win_summary, systems, win_ai))

    # --- Linux
    la = DemoLinuxAnalyzer(PERIOD, rnd)
    la.output_dir = reports_dir
    lin = la.run()
    report_data = {
        "l4": la.analyze_l4_deviation(),
        "daily_traffic": {d: dict(v) for d, v in la.daily_traffic.items()},
        "daily_errors": dict(la.daily_errors),
        "servers": dict(la.servers_data),
        "failed_nodes": dict(la.failed_nodes),
    }
    lin_ai, lin_src = resolve_ai(
        "linux", build_linux_digest(PERIOD["label"], report_data, linux_analyzer.classify_noise_line), args.refresh_ai)
    lin_summary = ["- [AI] " + ln for ln in lin_ai] + [""] + lin["summary_lines"]
    _save(os.path.join(email_dir, "linux.html"), build_linux_email_html(PERIOD["label"], report_data, lin_summary, lin_ai))

    key = PERIOD["key"]
    manifest = {
        "source": "demo",
        "label": "데모 (합성 로그)",
        "period_label": PERIOD["label"],
        "period_key": key,
        "ai_source": {"windows": win_src, "linux": lin_src},
        "windows": {
            "title": "E-OUT, IN-OUT 시스템 통합 로그 리포트 (Windows)",
            "email": "email/windows.html",
            "zip": "Report_WIN_%s.zip" % key,
            "reports": [{"title": "Windows 목차", "href": "reports/index_%s.html" % key}] + [
                {"title": name, "href": "reports/Report_%s_%s.html" % (name, key)} for name, _ in systems],
        },
        "linux": {
            "title": "E-BIZ 시스템 통합 로그 리포트 (Linux)",
            "email": "email/linux.html",
            "zip": "Report_EBIZ_%s.zip" % key,
            "reports": [{"title": "Linux 통합 (L4·노드별)", "href": "reports/Report_EBIZ_%s.html" % key}],
        },
    }
    _save(os.path.join(DOCS_DIR, "manifest.json"), json.dumps(manifest, ensure_ascii=False, indent=2))
    print("\n[데모] docs/demo/ 생성 완료 — AI 요약 출처:", manifest["ai_source"])


def _save(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
