import os
import re
import sys
from collections import Counter
from datetime import datetime

from ai_summary import build_win_digest, generate_ai_summary
from cli_common import build_arg_parser, is_auto_mode, resolve_period_from_args
from mail_sender import load_config, maybe_send_report
from period_utils import get_output_subdir, iter_dates
from report_builder import build_index, build_win_email_html, build_win_report

# ==========================================
# 1. 설정
# ==========================================
LOG_CONFIG = {
    "NGINX": {
        "path": r"C:\Tools\nginx-1.24.0\logs",
        "patterns": [
            "403", "404", "500", "401", "/admin", "/login", "Exception", "ERROR",
            "wp-", "phpmyadmin", ".env", "passwd", ".git", ".bak", "cmd", "shell",
        ],
        "noise_patterns": ["refresh-token"],
        "exclude": "GoogleStackdriverMonitoring-UptimeChecks",
        "date_format": "nginx",
    },
    "TOMCAT_EOUT": {
        "path": r"C:\Tools\apache-tomcat-9.0.82\logs",
        "patterns": [
            "Exception", "ERROR", "unauthorized", "denied", "fail", "NotFound",
            "shutdown", "critical", "security",
        ],
        "file_types": ["catalina", "localhost", "host-manager", "manager", "localhost_access_log"],
        "date_format": "tomcat",
    },
    "TOMCAT_INOUT": {
        "path": r"C:\Tools\apache-tomcat-9.0.82-inout\logs",
        "patterns": [
            "Exception", "ERROR", "unauthorized", "denied", "fail", "NotFound",
            "shutdown", "critical", "security",
        ],
        "file_types": ["catalina", "localhost", "host-manager", "manager", "localhost_access_log"],
        "date_format": "tomcat",
    },
}

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
MONTH_ABBR = {v: k for k, v in MONTH_MAP.items()}

NGINX_TS_RE = re.compile(r"\[(\d{2})/(\w{3})/(\d{4}):(\d{2}):\d{2}:\d{2}")
NGINX_ACCESS_RE = re.compile(r'^(\S+)\s+.*?"[A-Z]+\s+([^"]*?)"\s+(\d{3})\s')
TOMCAT_TS_RE = re.compile(r"(\d{2})-(\w{3})-(\d{4})\s+(\d{2}):")
TOMCAT_FILE_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _parse_nginx_date(line: str):
    m = NGINX_TS_RE.search(line)
    if not m:
        return None, None
    day, mon, year, hour = m.group(1), m.group(2), m.group(3), m.group(4)
    month = MONTH_MAP.get(mon)
    if not month:
        return None, None
    try:
        d = datetime(int(year), month, int(day)).date()
        return d, hour
    except ValueError:
        return None, None


def _parse_tomcat_date(line: str):
    m = TOMCAT_TS_RE.search(line)
    if not m:
        return None, None
    day, mon, year, hour = m.group(1), m.group(2), m.group(3), m.group(4)
    month = MONTH_MAP.get(mon)
    if not month:
        return None, None
    try:
        d = datetime(int(year), month, int(day)).date()
        return d, hour
    except ValueError:
        return None, None


def _parse_nginx_access(line: str):
    m = NGINX_ACCESS_RE.match(line)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return "", "", ""


def _matched_keywords(line: str, patterns: list) -> list:
    lower = line.lower()
    return [k for k in patterns if k.lower() in lower]


def _is_noise(line: str, keywords: list, noise_patterns: list) -> bool:
    if not noise_patterns:
        return False
    lower = line.lower()
    has_401 = "401" in keywords or re.search(r'\s401\s', line)
    return bool(has_401 and any(p.lower() in lower for p in noise_patterns))


def _file_in_period(filename: str, start, end, date_format: str) -> bool:
    if date_format == "nginx":
        return filename in ("access.log", "error.log")
    m = TOMCAT_FILE_DATE_RE.search(filename)
    if not m:
        return False
    try:
        fd = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        return start <= fd <= end
    except ValueError:
        return False


class WindowsLogAnalyzer:
    def __init__(self, period: dict):
        self.period = period
        self.start = period["start"]
        self.end = period["end"]
        self.period_key = period["key"]
        self.period_label = period["label"]

        base_path = os.path.dirname(os.path.abspath(
            sys.executable if getattr(sys, "frozen", False) else __file__
        ))
        subdir = get_output_subdir(period["period_type"])
        self.output_dir = os.path.join(base_path, "reports", subdir)
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"[알림] 리포트 저장 폴더: {self.output_dir}")

    def parse_logs(self, sys_name: str, config: dict) -> dict | None:
        print(f"\n>>> {sys_name} 분석 시작 (경로: {config['path']})")
        path = config["path"]
        keywords = config["patterns"]
        exclude = config.get("exclude")
        noise_patterns = config.get("noise_patterns", [])
        file_types = config.get("file_types", [])
        date_format = config["date_format"]

        entries = []
        noise_entries = []

        if not os.path.exists(path):
            print("   [경고] 해당 경로를 찾을 수 없습니다.")
            return None

        found_file_count = 0
        for filename in os.listdir(path):
            if date_format == "tomcat":
                if not any(t in filename for t in file_types):
                    continue
            if not _file_in_period(filename, self.start, self.end, date_format):
                continue

            found_file_count += 1
            file_path = os.path.join(path, filename)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if exclude and exclude in line:
                            continue

                        if date_format == "nginx":
                            log_date, hour = _parse_nginx_date(line)
                        else:
                            log_date, hour = _parse_tomcat_date(line)

                        if log_date is None or not (self.start <= log_date <= self.end):
                            continue

                        matched = _matched_keywords(line, keywords)
                        if not matched:
                            continue

                        ip, url, status = "", "", ""
                        if date_format == "nginx" and filename == "access.log":
                            ip, url, status = _parse_nginx_access(line)
                        elif status == "":
                            sm = re.search(r'\s(\d{3})\s', line)
                            if sm:
                                status = sm.group(1)

                        entry = {
                            "file": filename,
                            "date": log_date.isoformat(),
                            "hour": hour or "",
                            "keywords": matched,
                            "ip": ip,
                            "status": status,
                            "url": url,
                            "raw": line.strip(),
                            "is_noise": _is_noise(line, matched, noise_patterns),
                        }
                        if entry["is_noise"]:
                            noise_entries.append(entry)
                        else:
                            entries.append(entry)
            except Exception as e:
                print(f"   [오류] 파일 읽기 실패 ({filename}): {e}")

        if found_file_count == 0:
            print("   [알림] 분석 대상 파일을 찾지 못했습니다.")
            return None

        return self._aggregate_and_save(sys_name, entries, noise_entries)

    def _aggregate_and_save(self, sys_name: str, entries: list, noise_entries: list) -> dict:
        breakdown = Counter()
        hourly = Counter()
        daily = Counter()
        ip_counter = Counter()
        url_counter = Counter()

        for e in entries:
            for k in e["keywords"]:
                breakdown[k] += 1
            if e["hour"]:
                hourly[e["hour"]] += 1
            daily[e["date"]] += 1
            if e["ip"]:
                ip_counter[e["ip"]] += 1
            if e["url"]:
                url_counter[e["url"]] += 1

        day_count = len(iter_dates(self.start, self.end))
        data = {
            "period_key": self.period_key,
            "main_count": len(entries),
            "noise_count": len(noise_entries),
            "day_count": day_count,
            "breakdown": dict(breakdown),
            "hourly": dict(hourly),
            "daily": dict(daily),
            "top_ips": ip_counter.most_common(10),
            "top_urls": url_counter.most_common(10),
            "entries": entries,
            "noise_entries": noise_entries,
        }

        out_path = os.path.join(self.output_dir, f"Report_{sys_name}_{self.period_key}.html")
        build_win_report(out_path, sys_name, self.period_label, data)
        print(f"   [완료] 리포트 저장: {out_path}")
        print(f"   주요 탐지 {len(entries):,}건 / 노이즈 {len(noise_entries):,}건")
        return data

    def run(self, ai_cfg=None) -> dict:
        links = []
        systems_summary = []
        systems_data = []
        for system, cfg in LOG_CONFIG.items():
            result = self.parse_logs(system, cfg)
            if result is not None:
                links.append((
                    system,
                    f"Report_{system}_{self.period_key}.html",
                    f"주요 {result['main_count']:,}건",
                ))
                systems_summary.append(
                    f"- {system}: 주요 {result['main_count']:,}건 / 노이즈 {result['noise_count']:,}건"
                )
                systems_data.append((system, result))

        index_path = None
        if links:
            index_path = os.path.join(self.output_dir, f"index_{self.period_key}.html")
            build_index(index_path, self.period_label, self.period_key, links)
            print(f"\n[완료] 목차 페이지: {index_path}")

        html_body = None
        summary_lines = systems_summary or ["- 분석 대상 없음"]
        if systems_data:
            ai_lines = generate_ai_summary(ai_cfg, build_win_digest(self.period_label, systems_data))
            if ai_lines:
                summary_lines = ["- [AI] " + ln for ln in ai_lines] + [""] + summary_lines
            html_body = build_win_email_html(self.period_label, summary_lines, systems_data, ai_lines)

        return {
            "period_key": self.period_key,
            "period_label": self.period_label,
            "output_dir": self.output_dir,
            "index_path": index_path,
            "summary_lines": summary_lines,
            "html_body": html_body,
        }


def main(argv=None) -> int:
    parser = build_arg_parser("Windows 로그 분석 도구")
    args = parser.parse_args(argv)
    auto = is_auto_mode(args)

    print("==========================================")
    print("   시스템 로그 통합 분석 도구 v2.1")
    print("==========================================\n")

    try:
        period = resolve_period_from_args(args)
        if not period:
            return 1
        print(f"\n분석 기간: {period['label']}")
        ai_cfg = None
        if not args.no_ai:
            try:
                ai_cfg = load_config(args.config).get("ai")
            except Exception as e:
                print(f"   [AI 요약] 설정 파일을 읽지 못해 건너뜀: {e}")
        result = WindowsLogAnalyzer(period).run(ai_cfg)
        print("\n모든 분석 작업이 종료되었습니다.")

        maybe_send_report(
            config_path=args.config,
            send_email=not args.no_email,
            platform="Windows",
            period_key=result["period_key"],
            period_label=result["period_label"],
            report_dir=result["output_dir"],
            summary_lines=result["summary_lines"],
            html_body=result["html_body"],
            test_email=args.test_email,
        )
        return 0
    except Exception as e:
        print(f"\n[치명적 오류 발생] {e}")
        return 1
    finally:
        if not auto:
            print("\n" + "=" * 42)
            input("종료하려면 엔터 키를 누르세요...")


if __name__ == "__main__":
    sys.exit(main())
