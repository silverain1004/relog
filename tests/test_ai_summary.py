"""ai_summary 모듈 테스트 — 실제 API는 호출하지 않고 urlopen을 가짜로 바꿔 검증."""
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

import ai_summary
from linux_analyzer import classify_noise_line
from report_builder import build_linux_email_html

LINUX_DATA = {
    "l4": {"web1": 1200, "web2": 300, "dev_rate": 60.0, "status": "편차 심함"},
    "daily_traffic": {"2026-11-02": {"WEB1": 600, "WEB2": 150}, "2026-11-03": {"WEB1": 600, "WEB2": 150}},
    "daily_errors": {"2026-11-02": 3, "2026-11-03": 40},
    "servers": {
        "WEB1": {"traffic": 1200, "error_count": 2, "categories": {"WordPress 스캔": 1, "기타(미분류)": 1},
                 "errors": ['GET /wp-login.php 404', '10.1.2.3 POST /api/order 500 admin@corp.com']},
    },
    "failed_nodes": {"WAS2": "timed out 10.20.30.22"},
}


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class MaskTest(unittest.TestCase):
    def test_mask_ip_and_email(self):
        self.assertEqual(ai_summary.mask_text("10.20.30.11 a@b.com"), "10.20.x.x ***@***")


class DigestTest(unittest.TestCase):
    def test_linux_digest_masks_and_samples_unclassified_only(self):
        d = ai_summary.build_linux_digest("2026-W45", LINUX_DATA, classify_noise_line)
        self.assertIn("편차 60.0%", d)
        self.assertIn("/api/order 500", d)
        self.assertNotIn("wp-login", d)        # 알려진 스캔은 샘플에서 제외
        self.assertNotIn("10.20.30.22", d)   # 내부 IP 마스킹
        self.assertNotIn("admin@corp.com", d)


class GenerateTest(unittest.TestCase):
    def test_disabled_returns_none(self):
        self.assertIsNone(ai_summary.generate_ai_summary({"enabled": False}, "x"))

    def test_missing_key_returns_none(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(ai_summary.generate_ai_summary({"enabled": True, "api_key": "YOUR_KEY"}, "x"))

    def test_success_parses_lines(self):
        body = {"content": [{"type": "text", "text": "종합: 주의 — L4 편차가 큽니다.\n- WEB2 헬스체크 확인\n- WAS2 SSH 점검"}]}
        with mock.patch("urllib.request.urlopen", return_value=FakeResp(json.dumps(body).encode())) as m:
            lines = ai_summary.generate_ai_summary({"enabled": True, "api_key": "sk-test"}, "digest")
        self.assertEqual(lines, ["종합: 주의 — L4 편차가 큽니다.", "WEB2 헬스체크 확인", "WAS2 SSH 점검"])
        req = m.call_args[0][0]
        self.assertEqual(req.get_header("X-api-key"), "sk-test")

    def test_network_error_returns_none(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("no route")):
            self.assertIsNone(ai_summary.generate_ai_summary({"enabled": True, "api_key": "sk-test"}, "x"))


class EmailRenderTest(unittest.TestCase):
    def test_ai_box_rendered_when_present(self):
        html = build_linux_email_html("W45", LINUX_DATA, [], ["종합: 위험 — 장애 징후", "조치 필요"])
        self.assertIn("AI 요약 (Claude)", html)
        self.assertIn("#c0392b", html)

    def test_no_ai_box_when_absent(self):
        self.assertNotIn("AI 요약", build_linux_email_html("W45", LINUX_DATA, []))


if __name__ == "__main__":
    unittest.main()
