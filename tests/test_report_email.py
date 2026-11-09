"""linux_analyzer의 노이즈 분류 + report_builder의 이메일 렌더링 스모크 테스트.
stdlib unittest만 사용 (서버가 Python 3.6.8이라 외부 테스트 프레임워크 미도입)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from linux_analyzer import classify_noise_line
from report_builder import build_linux_email_html, build_win_email_html


class ClassifyNoiseLineTest(unittest.TestCase):
    def test_fortios_scan(self):
        self.assertEqual(
            classify_noise_line('GET /remote/logincheck HTTP/1.1" 404'),
            "FortiOS VPN 취약점 스캔",
        )

    def test_wordpress_scan(self):
        self.assertEqual(
            classify_noise_line('POST /xmlrpc.php HTTP/1.1" 403'),
            "WordPress 스캔",
        )

    def test_generic_recon_scan(self):
        self.assertEqual(
            classify_noise_line('GET /.env HTTP/1.1" 404'),
            "일반 정찰성 스캔",
        )

    def test_unclassified_falls_back(self):
        self.assertEqual(
            classify_noise_line('GET /some/random/app/path HTTP/1.1" 500'),
            "기타(미분류)",
        )

    def test_is_case_insensitive(self):
        self.assertEqual(
            classify_noise_line('GET /WP-LOGIN.PHP HTTP/1.1" 404'),
            "WordPress 스캔",
        )


def _sample_linux_data(unclassified_count=0):
    categories = {"WordPress 스캔": 3}
    if unclassified_count:
        categories["기타(미분류)"] = unclassified_count
    return {
        "l4": {"web1": 100, "web2": 90, "dev_rate": 5.0, "status": "정상"},
        "daily_traffic": {"2026-07-13": {"WEB1": 50, "WEB2": 45}},
        "daily_errors": {"2026-07-13": 3},
        "servers": {
            "WEB1": {"traffic": 100, "errors": ["GET /wp-login.php"], "error_count": 3, "categories": categories},
        },
        "failed_nodes": {},
    }


class BuildLinuxEmailHtmlTest(unittest.TestCase):
    def test_renders_without_error(self):
        html = build_linux_email_html("2026년 29주", _sample_linux_data(), ["- 정상"])
        self.assertIn("<html", html)
        self.assertIn("E-BIZ", html)

    def test_below_threshold_has_no_guidance_alert(self):
        html = build_linux_email_html("2026년 29주", _sample_linux_data(unclassified_count=1), ["- 정상"])
        self.assertIn("특이사항 없음", html)

    def test_at_or_above_threshold_triggers_guidance_alert(self):
        html = build_linux_email_html("2026년 29주", _sample_linux_data(unclassified_count=10), ["- 정상"])
        self.assertIn("미분류 노이즈", html)

    def test_failed_node_triggers_guidance_alert(self):
        data = _sample_linux_data()
        data["failed_nodes"] = {"WAS1": "SSH timeout"}
        html = build_linux_email_html("2026년 29주", data, ["- 정상"])
        self.assertIn("로그 수집 실패", html)


class BuildWinEmailHtmlTest(unittest.TestCase):
    def test_renders_without_error(self):
        systems = [
            ("E-OUT", {
                "main_count": 2, "noise_count": 1, "day_count": 7,
                "breakdown": {"401": 1}, "daily": {"2026-07-13": 1},
                "top_ips": [("1.2.3.4", 1)], "top_urls": [("/x", 1)],
                "entries": ["sample log line"],
            }),
        ]
        html = build_win_email_html("2026년 29주", ["- 정상"], systems)
        self.assertIn("<html", html)
        self.assertIn("E-OUT", html)


if __name__ == "__main__":
    unittest.main()
