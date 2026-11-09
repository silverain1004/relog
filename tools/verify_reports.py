"""로컬 샘플 로그로 HTML 리포트 생성 검증 (python tools/verify_reports.py)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import shutil
import win_analyzer as wa  # noqa: E402
from period_utils import get_auto_weekly_period, parse_period_input, parse_weekly_from_date
from mail_sender import zip_reports

TEST_LOGS = os.path.join(ROOT, "tests", "fixtures", "logs")
REPORTS = os.path.join(ROOT, "app", "reports")  # 분석기는 자기 폴더 아래 reports/에 쓴다

wa.LOG_CONFIG["NGINX"]["path"] = os.path.join(TEST_LOGS, "nginx")
wa.LOG_CONFIG["TOMCAT_EOUT"]["path"] = os.path.join(TEST_LOGS, "tomcat")
wa.LOG_CONFIG["TOMCAT_INOUT"]["path"] = os.path.join(TEST_LOGS, "tomcat")

period = parse_weekly_from_date("2026-05-12")
assert period["week"] == 20
assert period["key"] == "2026W20"
analyzer = wa.WindowsLogAnalyzer(period)
analyzer.run()

weekly_dir = os.path.join(REPORTS, "weekly")
assert os.path.exists(os.path.join(weekly_dir, "index_2026W20.html"))
assert os.path.exists(os.path.join(weekly_dir, "Report_NGINX_2026W20.html"))

with open(os.path.join(weekly_dir, "Report_NGINX_2026W20.html"), encoding="utf-8") as f:
    html = f.read()
assert "26시" not in html
assert "08시" in html or "14시" in html
assert "refresh-token" in html
assert "주요 탐지" in html

period_m = parse_period_input("monthly", "2026", "05")
analyzer_m = wa.WindowsLogAnalyzer(period_m)
analyzer_m.run()
assert os.path.exists(os.path.join(REPORTS, "monthly", "index_202605.html"))

from report_builder import build_linux_report
linux_path = os.path.join(REPORTS, "weekly", "Report_EBIZ_2026W20_test.html")
build_linux_report(linux_path, period["label"], {
    "l4": {"web1": 1000, "web2": 900, "dev_rate": 5.3, "status": "정상"},
    "daily_traffic": {"2026-05-11": {"WEB1": 500, "WEB2": 450}, "2026-05-12": {"WEB1": 500, "WEB2": 450}},
    "daily_errors": {"2026-05-11": 3, "2026-05-12": 1},
    "servers": {"WEB1": {"traffic": 1000, "errors": ["error line"], "error_count": 1}},
})
assert os.path.exists(linux_path)

# auto period + CLI
auto = get_auto_weekly_period(__import__("datetime").date(2026, 6, 23))
assert auto["key"]  # 직전 주

exit_code = wa.main(["--auto", "weekly", "--no-email", "--date", "2026-05-18"])
assert exit_code == 0

zip_path = zip_reports(weekly_dir, "2026W20", "WIN")
assert os.path.exists(zip_path)

print("ALL TESTS PASSED")
