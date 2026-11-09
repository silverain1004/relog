"""E-BIZ Linux 이중화 로그 분석. Python 3.6 호환 유지 (WEB1 서버가 3.6.8)."""
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Optional

try:
    import paramiko
except ImportError:
    paramiko = None

from ai_summary import build_linux_digest, generate_ai_summary
from cli_common import build_arg_parser, resolve_period_from_args
from mail_sender import load_config, maybe_send_report
from period_utils import get_output_subdir, iter_dates
from report_builder import build_linux_email_html, build_linux_report

DEFAULT_SSH_TIMEOUT = 10
DEFAULT_L4_THRESHOLD = 15

EXCLUDE_FILTER = "GoogleHC|GoogleStackdriverMonitoring|UptimeChecks"
ERROR_PATTERNS = "error|crit|alert|emerg|Exception|WARNING|fail|denied"
NOISE_PATTERNS = ["refresh-token"]

# 알려진 인터넷 배경 스캔(취약점 스캐너) 시그니처 — 순서대로 첫 매치를 채택.
# 여기에 안 걸리면 "기타(미분류)"로 남아 실제 애플리케이션 에러 가능성을 사람이 봐야 함.
SCAN_SIGNATURE_GROUPS = (
    ("FortiOS VPN 취약점 스캔", (
        "remote/logincheck", "ftnt-icons", "lang/custom/sbin/init",
        "lang/legacy/filechecksum", "migadmin/lang/legacy", "login?redir=/ng",
    )),
    ("WordPress 스캔", (
        "xmlrpc.php", "wp-login", "wp-admin", "wp-json", "wp-content",
    )),
    ("일반 정찰성 스캔", (
        "/.env", "/.git/", "phpmyadmin", "actuator", "/.aws", "not.found",
    )),
)


def classify_noise_line(line: str) -> str:
    lower = line.lower()
    for label, patterns in SCAN_SIGNATURE_GROUPS:
        if any(p in lower for p in patterns):
            return label
    return "기타(미분류)"


def load_linux_config(config_path: Optional[str]) -> dict:
    config = load_config(config_path)
    linux = config.get("linux")
    if not linux:
        raise RuntimeError(
            "config.json에 'linux' 섹션이 없습니다. config.example.json의 linux 섹션을 복사해 채워주세요."
        )
    for key in ("ssh_user", "key_path", "servers", "log_paths"):
        if key not in linux:
            raise RuntimeError(f"config.json의 linux 섹션에 '{key}' 항목이 없습니다.")
    return linux


def _is_noise_line(line: str) -> bool:
    lower = line.lower()
    return "401" in line and any(p in lower for p in NOISE_PATTERNS)


def _filter_noise(lines: list) -> list:
    return [ln for ln in lines if not _is_noise_line(ln)]


class LinuxMasterAnalyzer:
    def __init__(self, period: dict, linux_cfg: dict):
        self.period = period
        self.start = period["start"]
        self.end = period["end"]
        self.period_key = period["key"]
        self.period_label = period["label"]
        self.dates = iter_dates(self.start, self.end)

        self.servers = linux_cfg["servers"]
        self.ssh_user = linux_cfg["ssh_user"]
        self.key_path = linux_cfg["key_path"]
        self.log_paths = linux_cfg["log_paths"]
        self.ssh_timeout = int(linux_cfg.get("ssh_timeout_sec", DEFAULT_SSH_TIMEOUT))
        self.l4_threshold = float(linux_cfg.get("l4_threshold_pct", DEFAULT_L4_THRESHOLD))

        base_path = os.path.dirname(os.path.abspath(
            sys.executable if getattr(sys, "frozen", False) else __file__
        ))
        subdir = get_output_subdir(period["period_type"])
        self.output_dir = os.path.join(base_path, "reports", subdir)
        os.makedirs(self.output_dir, exist_ok=True)

        self.traffic_stats = defaultdict(int)
        self.daily_traffic = defaultdict(lambda: defaultdict(int))
        self.daily_errors = defaultdict(int)
        self.servers_data = defaultdict(lambda: {"traffic": 0, "errors": [], "error_count": 0, "categories": Counter()})
        self.ssh_clients = {}
        self.failed_nodes = {}
        self.ai_cfg = None  # main()에서 config.json의 ai 섹션을 넣어줌

    def get_ssh_client(self, ip):
        if ip in self.ssh_clients:
            return self.ssh_clients[ip]
        if paramiko is None:
            raise RuntimeError("paramiko가 설치되지 않았습니다. pip install -r requirements.txt")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            ip,
            username=self.ssh_user,
            key_filename=self.key_path,
            timeout=self.ssh_timeout,
        )
        self.ssh_clients[ip] = client
        return client

    def close_ssh_clients(self):
        for client in self.ssh_clients.values():
            try:
                client.close()
            except Exception:
                pass
        self.ssh_clients.clear()

    def _run_cmd(self, server: dict, cmd: str) -> str:
        if server["is_local"]:
            # capture_output/text 인자는 3.7+ — 3.6에서는 PIPE/universal_newlines 사용
            result = subprocess.run(
                cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, timeout=self.ssh_timeout * 6,
            )
            return result.stdout.strip()
        ssh = self.get_ssh_client(server["ip"])
        _, stdout, _ = ssh.exec_command(cmd, timeout=self.ssh_timeout * 6)
        return stdout.read().decode().strip()

    def _fetch_day(self, server: dict, day, day_idx: int, total_days: int):
        name = server["name"]
        date_str = day.strftime("%Y-%m-%d")
        access_fmt = day.strftime("%d/%b/%Y")     # nginx access.log: 20/Jul/2026
        errlog_fmt = day.strftime("%Y/%m/%d")     # nginx error.log: 2026/07/20
        ebiz_fmt = day.strftime("%Y%m%d")

        print(f"   [{day_idx}/{total_days}] {name} - {date_str} 수집 중...")

        if server["role"] == "WEB":
            # 실서버는 일별 rotate + gzip(access.log-YYYYMMDD.gz) — zgrep은 평문/gz 모두 읽음.
            # 해당 날짜의 라인은 그날 파일 또는 다음날 새벽 rotate된 파일에 있으므로 셋 다 후보로.
            # 날짜 문자열로 다시 거르기 때문에 후보가 넓어도 중복 집계는 없음.
            next_fmt = (day + timedelta(days=1)).strftime("%Y%m%d")
            acc = self.log_paths["WEB"]["access"]
            err = self.log_paths["WEB"]["error"]
            acc_files = f"{acc} {acc}-{ebiz_fmt}* {acc}-{next_fmt}*"
            err_files = f"{err} {err}-{ebiz_fmt}* {err}-{next_fmt}*"
            cmd_traffic = (
                f"zgrep -h '{access_fmt}' {acc_files} 2>/dev/null "
                f"| grep -Ev '{EXCLUDE_FILTER}' | wc -l"
            )
            cmd_error = (
                f"zgrep -hEi '{ERROR_PATTERNS}' {err_files} 2>/dev/null "
                f"| grep '{errlog_fmt}' | head -n 500"
            )
        else:
            cat_path = self.log_paths["WAS"]["catalina"].format(date_str)
            ebiz_path = self.log_paths["WAS"]["ebiz"].format(ebiz_fmt)
            cmd_traffic = f"grep -c '' {ebiz_path} 2>/dev/null || echo 0"
            cmd_error = f"grep -Ei '{ERROR_PATTERNS}' {cat_path} 2>/dev/null | head -n 500"

        traffic = self._run_cmd(server, cmd_traffic)
        errors_raw = self._run_cmd(server, cmd_error)

        traffic_n = int(traffic) if traffic and traffic.isdigit() else 0
        error_lines = [ln for ln in errors_raw.split("\n") if ln.strip()] if errors_raw else []
        error_lines = _filter_noise(error_lines)

        self.traffic_stats[name] += traffic_n
        self.daily_traffic[date_str][name] += traffic_n
        self.daily_errors[date_str] += len(error_lines)

        srv = self.servers_data[name]
        srv["traffic"] += traffic_n
        srv["errors"].extend(error_lines)
        srv["error_count"] += len(error_lines)
        for ln in error_lines:
            srv["categories"][classify_noise_line(ln)] += 1

    def analyze_l4_deviation(self) -> dict:
        web1 = self.traffic_stats.get("WEB1", 0)
        web2 = self.traffic_stats.get("WEB2", 0)
        total = web1 + web2
        if total == 0:
            return {"web1": web1, "web2": web2, "dev_rate": 0, "status": "데이터 없음"}

        dev_rate = abs(web1 - web2) / total * 100
        status = "정상" if dev_rate < self.l4_threshold else "편차 심함"
        return {"web1": web1, "web2": web2, "dev_rate": dev_rate, "status": status}

    def run(self) -> dict:
        total_days = len(self.dates)
        print(f"\n분석 기간: {self.period_label} ({total_days}일)")

        try:
            for day_idx, day in enumerate(self.dates, 1):
                for server in self.servers:
                    name = server["name"]
                    if name in self.failed_nodes:
                        continue
                    try:
                        self._fetch_day(server, day, day_idx, total_days)
                    except Exception as e:
                        if not server["is_local"] and server["ip"] not in self.ssh_clients:
                            # 접속 자체가 안 되는 노드는 남은 날짜를 건너뜀
                            self.failed_nodes[name] = str(e)
                            print(f"   [오류] {name} 접속 실패 - 이후 수집 건너뜀: {e}")
                        else:
                            print(f"   [오류] {name} {day}: {e}")
        finally:
            self.close_ssh_clients()

        l4 = self.analyze_l4_deviation()
        report_data = {
            "l4": l4,
            "daily_traffic": {d: dict(v) for d, v in self.daily_traffic.items()},
            "daily_errors": dict(self.daily_errors),
            "servers": dict(self.servers_data),
            "failed_nodes": dict(self.failed_nodes),
        }

        out_path = os.path.join(self.output_dir, f"Report_EBIZ_{self.period_key}.html")
        build_linux_report(out_path, self.period_label, report_data)

        summary_lines = [
            f"- L4: WEB1({l4['web1']:,}) vs WEB2({l4['web2']:,}) | 편차 {l4['dev_rate']:.1f}% [{l4['status']}]",
        ]
        for name, srv in self.servers_data.items():
            summary_lines.append(f"- {name}: 트래픽 {srv['traffic']:,} / 노이즈 {srv['error_count']:,}건")
        for name, reason in self.failed_nodes.items():
            summary_lines.append(f"- [수집 실패] {name}: {reason}")

        ai_lines = generate_ai_summary(
            self.ai_cfg, build_linux_digest(self.period_label, report_data, classify_noise_line)
        )
        if ai_lines:
            summary_lines = ["- [AI] " + ln for ln in ai_lines] + [""] + summary_lines
        html_body = build_linux_email_html(self.period_label, report_data, summary_lines, ai_lines)

        print("\n" + "=" * 50)
        print(f"E-BIZ 통합 분석 리포트 ({self.period_label})")
        print("=" * 50)
        print(f"\n[1] L4 트래픽: WEB1({l4['web1']:,}) vs WEB2({l4['web2']:,}) | 편차 {l4['dev_rate']:.1f}% [{l4['status']}]")
        print("\n[2] 노드별 노이즈 합계")
        for name, srv in self.servers_data.items():
            print(f"   - {name}: {srv['error_count']:,}건")
            for label, cnt in srv["categories"].most_common():
                print(f"       · {label}: {cnt:,}건")
        if self.failed_nodes:
            print("\n[3] 수집 실패 노드")
            for name, reason in self.failed_nodes.items():
                print(f"   - {name}: {reason}")
        print(f"\n[완료] HTML 리포트: {out_path}")

        return {
            "period_key": self.period_key,
            "period_label": self.period_label,
            "output_dir": self.output_dir,
            "report_path": out_path,
            "summary_lines": summary_lines,
            "html_body": html_body,
        }


def main(argv=None) -> int:
    parser = build_arg_parser("E-BIZ Linux 로그 통합 분석")
    args = parser.parse_args(argv)

    print("==========================================")
    print("   E-BIZ Linux 로그 통합 분석 v2.2")
    print("==========================================\n")

    try:
        linux_cfg = load_linux_config(args.config)
        period = resolve_period_from_args(args)
        if not period:
            return 1
        analyzer = LinuxMasterAnalyzer(period, linux_cfg)
        if not args.no_ai:
            analyzer.ai_cfg = load_config(args.config).get("ai")
        result = analyzer.run()

        maybe_send_report(
            config_path=args.config,
            send_email=not args.no_email,
            platform="Linux",
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


if __name__ == "__main__":
    sys.exit(main())
