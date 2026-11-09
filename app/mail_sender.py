"""SMTP 메일 발송 및 리포트 ZIP 생성. Python 3.6 호환 유지 (WEB1 서버가 3.6.8)."""
import json
import os
import smtplib
import zipfile
from typing import Optional
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def get_base_dir() -> str:
    import sys
    return os.path.dirname(os.path.abspath(
        sys.executable if getattr(sys, "frozen", False) else __file__
    ))


def default_config_path() -> str:
    return os.path.join(get_base_dir(), "config.json")


def load_config(path: Optional[str] = None) -> dict:
    config_path = path or default_config_path()
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def zip_reports(report_dir: str, period_key: str, platform: str) -> str:
    """index_*.html 및 Report_*.html 을 ZIP으로 묶음."""
    zip_name = f"Report_{platform}_{period_key}.zip"
    zip_path = os.path.join(report_dir, zip_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(report_dir):
            if not fname.endswith(".html"):
                continue
            if period_key not in fname:
                continue
            zf.write(os.path.join(report_dir, fname), arcname=fname)
    return zip_path


def build_summary_body(platform: str, period_label: str, summary_lines: list) -> str:
    lines = [
        f"플랫폼: {platform}",
        f"분석 기간: {period_label}",
        f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        *summary_lines,
        "",
        "첨부 ZIP 파일의 index_*.html 을 열면 전체 대시보드를 확인할 수 있습니다.",
    ]
    return "\n".join(lines)


def send_report_email(
    config: dict,
    zip_path: str,
    platform: str,
    period_label: str,
    summary_lines: list,
    html_body: Optional[str] = None,
    test_email: bool = False,
) -> None:
    email_cfg = config.get("email", {})
    if not email_cfg.get("enabled", False):
        print("[알림] 메일 발송 비활성화 (email.enabled=false)")
        return

    host = email_cfg["smtp_host"]
    port = int(email_cfg.get("smtp_port", 587))
    use_tls = email_cfg.get("use_tls", True)
    username = email_cfg.get("username", "")
    password = email_cfg.get("password", "")
    from_addr = email_cfg.get("from_addr", username)
    to_addrs = email_cfg.get("to_addrs", [])
    prefix = email_cfg.get("subject_prefix", "[로그리포트]")

    if test_email:
        to_addrs = [from_addr]
        prefix = f"[TEST] {prefix}"

    if not to_addrs:
        raise ValueError("수신 주소(to_addrs)가 비어 있습니다.")

    subject = f"{prefix} {platform} {period_label}"
    body = build_summary_body(platform, period_label, summary_lines)

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    if html_body:
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alt)
    else:
        msg.attach(MIMEText(body, "plain", "utf-8"))

    with open(zip_path, "rb") as f:
        attachment = MIMEApplication(f.read(), Name=os.path.basename(zip_path))
    attachment["Content-Disposition"] = f'attachment; filename="{os.path.basename(zip_path)}"'
    msg.attach(attachment)

    print(f"[메일] 발송 중 → {', '.join(to_addrs)}")
    with smtplib.SMTP(host, port, timeout=60) as server:
        if use_tls:
            server.starttls()
        if username and password:
            server.login(username, password)
        server.sendmail(from_addr, to_addrs, msg.as_string())
    print(f"[완료] 메일 발송됨: {subject}")


def maybe_send_report(
    config_path: Optional[str],
    send_email: bool,
    platform: str,
    period_key: str,
    period_label: str,
    report_dir: str,
    summary_lines: list,
    html_body: Optional[str] = None,
    test_email: bool = False,
) -> None:
    if not send_email:
        print("[알림] --no-email 옵션으로 메일 발송 생략")
        return
    try:
        config = load_config(config_path)
        zip_path = zip_reports(report_dir, period_key, platform)
        send_report_email(
            config, zip_path, platform, period_label, summary_lines,
            html_body=html_body, test_email=test_email,
        )
    except FileNotFoundError as e:
        print(f"[경고] {e} — 메일 발송 생략")
    except Exception as e:
        print(f"[오류] 메일 발송 실패: {e}")
        raise
