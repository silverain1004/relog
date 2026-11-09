import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import mask_live as ml  # noqa: E402


WORDS = [(r"acmesteel", "customer"), (r"acme\b", "customer")]  # 테스트용 가짜 고객사


def _mask(text, deny=()):
    return ml.Masker(list(deny), WORDS).mask(text)


def test_ip_mapping_is_consistent_and_safe():
    m = ml.Masker([], WORDS)
    out = m.mask("172.31.200.7 then 93.184.216.34 then 172.31.200.7")
    a, _, b, _, c = out.split(" ")
    assert a == c and a.startswith("10.20.")
    assert b.startswith("198.18.")
    assert ml.leaks(out, [], WORDS) == []


def test_customer_domain_and_words():
    out = _mask('host: "vpn.acmesteel.co.kr" referer https://inout.acmesteel.co.kr/main acme')
    assert "acme" not in out.lower()
    assert "vpn.customer-1.example" in out and "inout.customer-1.example" in out
    assert ml.leaks(out, [], WORDS) == []


def test_email_query_jwt_ids_paths():
    out = _mask(
        "me@vntgcorp.com GET /api/x?token=abcdef&amp;page=2 "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig_part "
        "/users/1234567/info C:\\Users\\ops_kim\\Desktop /home/ops_lee/key.pem"
    )
    assert "user1@example.com" in out
    assert "token=***" in out and "page=2" in out
    assert "eyJ" not in out
    assert "/users/{id}/info" in out
    assert "ops_kim" not in out and "ops_lee" not in out
    assert ml.leaks(out, [], WORDS) == []


def test_paths_are_not_mistaken_for_tokens():
    line = 'open() "/usr/share/nginx/html/api/v2/static/not.found" failed'
    assert _mask(line) == line


def test_extra_deny_words_and_leak_detection():
    out = _mask("operator kimchulsoo restarted WIN-PRODAPP01", deny=["kimchulsoo", "WIN-PRODAPP01"])
    assert "kimchulsoo" not in out and "PRODAPP01" not in out
    assert ml.leaks("10.1.2.3 a@b.com x.acmesteel.co.kr", [], WORDS) != []


def test_eml_with_zip_is_extracted_and_masked(tmp_path):
    import io
    import json
    import subprocess
    import zipfile
    from email.message import EmailMessage

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Report_EBIZ_2026W44.html",
                    '<html><body><td>client: 203.0.113.50, host: "vpn.acmesteel.co.kr"</td></body></html>')
    msg = EmailMessage()
    msg["Subject"] = "[로그리포트] Linux 2026년 44주 (2026-10-26 ~ 2026-11-01)"
    msg.set_content("plain")
    msg.add_alternative("<html><body>분석 기간: 2026년 44주 (2026-10-26 ~ 2026-11-01) 172.31.200.7</body></html>",
                        subtype="html")
    msg.add_attachment(buf.getvalue(), maintype="application", subtype="octet-stream",
                       filename="Report_Linux_2026W44.zip")
    src = tmp_path / "src"
    src.mkdir()
    (src / "linux.eml").write_bytes(bytes(msg))
    out = tmp_path / "out"

    tool = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "mask_live.py")
    r = subprocess.run([sys.executable, tool, str(src), "--out", str(out)], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["linux"]["email"] == "email/linux.html"
    assert manifest["linux"]["reports"][0]["href"] == "reports/linux/Report_EBIZ_2026W44.html"
    assert manifest["period_label"].startswith("2026년 44주")
    report = (out / "reports" / "linux" / "Report_EBIZ_2026W44.html").read_text(encoding="utf-8")
    body = (out / "email" / "linux.html").read_text(encoding="utf-8")
    assert "acmesteel" not in report and "203.0.113" not in report and "172.31" not in body


def test_trim_log_rows_keeps_even_sample():
    rows = "".join("<tr data-keywords='404'><td>%d</td></tr>" % i for i in range(1000))
    html = '<table class="log-table" id="main-logs"><thead></thead><tbody>%s</tbody></table>' % rows
    out = ml.trim_log_rows(html, 100)
    assert out.count("<tr") == 101  # 안내 1줄 + 100줄
    assert "<td>0</td>" in out and "<td>990</td>" in out and "1,000건" in out
    assert ml.trim_log_rows(html, 5000) == html
