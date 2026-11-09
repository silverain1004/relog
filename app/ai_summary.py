"""Claude API로 리포트 'AI 요약'을 생성. Python 3.6 호환 유지 (WEB1 서버가 3.6.8).

- SDK 없이 urllib로 Messages API를 직접 호출한다 (anthropic SDK는 3.8+).
- 원본 로그를 통째로 보내지 않고 '집계 수치 + 마스킹한 샘플 몇 줄'만 보낸다.
- 키가 없거나 호출이 실패하면 None을 돌려주고, 리포트/메일은 기존대로 나간다.
"""
import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_TIMEOUT = 60
MAX_SAMPLE_LINES = 15
MAX_LINE_LEN = 300
MAX_OUTPUT_LINES = 6

_IPV4_RE = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

SYSTEM_PROMPT = """당신은 웹/WAS 서버를 운영하는 인프라 담당자를 돕는 로그 분석 보조입니다.
주간/월간 로그 집계 결과를 읽고, 바쁜 담당자가 메일 첫 화면에서 30초 안에 판단할 수 있도록 요약합니다.

출력 형식 (반드시 지킬 것):
- 첫 줄: "종합: 정상" 또는 "종합: 주의" 또는 "종합: 위험" 뒤에 " — " 와 한 문장 요약
- 이후 2~4줄: 각 줄은 "- "로 시작하는 특이사항 또는 권장 조치 한 문장
- 마크다운 제목/표/코드블록/굵게 표시 금지, 줄 수 최대 5줄

판단 기준:
- 알려진 스캔 시그니처(FortiOS, WordPress, 정찰성 스캔)와 refresh-token 401은 인터넷 배경 소음이므로 조치 불필요로 본다.
- '기타(미분류)' 샘플에 Exception, 500, DB/커넥션 오류, OutOfMemory 등 실제 애플리케이션 장애 징후가 있으면 우선 언급한다.
- L4 편차가 임계치를 넘거나 수집 실패 노드가 있으면 반드시 언급한다.
- 특정 날짜에 노이즈/트래픽이 급증했으면 날짜와 함께 언급한다.
- 데이터에 없는 사실은 추측하지 말고, 수치는 주어진 값만 사용한다."""


def mask_text(text: str) -> str:
    """IP 뒤 두 자리와 이메일을 가린다. (예: 10.20.30.11 -> 10.20.x.x)"""
    text = _IPV4_RE.sub(lambda m: f"{m.group(1)}.{m.group(2)}.x.x", text)
    return _EMAIL_RE.sub("***@***", text)


def _clip(line: str) -> str:
    line = mask_text(str(line).strip())
    return line if len(line) <= MAX_LINE_LEN else line[:MAX_LINE_LEN] + "…"


def build_linux_digest(period_label: str, data: dict, classify_fn=None) -> str:
    l4 = data.get("l4", {})
    out = [
        f"[플랫폼] Linux (E-BIZ, WEB 2대 + WAS 2대)",
        f"[기간] {period_label}",
        f"[L4] WEB1 {l4.get('web1', 0):,} / WEB2 {l4.get('web2', 0):,} / 편차 {l4.get('dev_rate', 0):.1f}% / 판정 {l4.get('status', '-')}",
    ]
    for name, srv in data.get("servers", {}).items():
        cats = ", ".join(f"{k} {v:,}" for k, v in dict(srv.get("categories", {})).items()) or "없음"
        out.append(f"[{name}] 트래픽 {srv.get('traffic', 0):,} / 노이즈 {srv.get('error_count', 0):,}건 ({cats})")
    for name, reason in data.get("failed_nodes", {}).items():
        out.append(f"[수집 실패] {name}: {mask_text(str(reason))}")

    daily_traffic = data.get("daily_traffic", {})
    if daily_traffic:
        out.append("[일별 WEB 트래픽] " + ", ".join(
            f"{d[5:]} {v.get('WEB1', 0) + v.get('WEB2', 0):,}" for d, v in sorted(daily_traffic.items())))
    daily_errors = data.get("daily_errors", {})
    if daily_errors:
        out.append("[일별 노이즈] " + ", ".join(f"{d[5:]} {v:,}" for d, v in sorted(daily_errors.items())))

    # 미분류(사람이 봐야 하는) 라인 위주로 샘플링
    for name, srv in data.get("servers", {}).items():
        lines = srv.get("errors", [])
        if classify_fn:
            lines = [ln for ln in lines if classify_fn(ln) == "기타(미분류)"]
        if lines:
            out.append(f"[{name} 미분류 샘플 {min(len(lines), MAX_SAMPLE_LINES)}/{len(lines)}줄]")
            out.extend("  " + _clip(ln) for ln in lines[:MAX_SAMPLE_LINES])
    return "\n".join(out)


def build_win_digest(period_label: str, systems: list) -> str:
    out = [f"[플랫폼] Windows (E-OUT / IN-OUT: NGINX + Tomcat 2종)", f"[기간] {period_label}"]
    for sys_name, data in systems:
        out.append(
            f"[{sys_name}] 주요 탐지 {data.get('main_count', 0):,}건 / 노이즈(refresh-token 401) "
            f"{data.get('noise_count', 0):,}건 / {data.get('day_count', 0)}일"
        )
        breakdown = data.get("breakdown", {})
        if breakdown:
            top = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)[:10]
            out.append("  키워드: " + ", ".join(f"{k} {v:,}" for k, v in top))
        daily = data.get("daily", {})
        if daily:
            out.append("  일별: " + ", ".join(f"{d[5:]} {v:,}" for d, v in sorted(daily.items())))
        if data.get("top_ips"):
            out.append("  Top IP: " + ", ".join(f"{mask_text(ip)} {n:,}" for ip, n in data["top_ips"][:5]))
        if data.get("top_urls"):
            out.append("  Top URL: " + ", ".join(f"{_clip(u)} {n:,}" for u, n in data["top_urls"][:5]))
        entries = data.get("entries", [])
        if entries:
            out.append(f"  샘플 {min(len(entries), 10)}/{len(entries)}줄:")
            out.extend("    " + _clip(e.get("raw", "") if isinstance(e, dict) else e) for e in entries[:10])
    return "\n".join(out)


def parse_summary(text: str) -> list:
    lines = []
    for raw in text.splitlines():
        line = raw.strip().strip("*").strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        if line.startswith("- ") or line.startswith("• "):
            line = line[2:].strip()
        lines.append(line)
    return lines[:MAX_OUTPUT_LINES]


def _resolve_api_key(ai_cfg: dict) -> Optional[str]:
    key = (ai_cfg or {}).get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not key or key.startswith("YOUR_"):
        return None
    return key


def generate_ai_summary(ai_cfg: Optional[dict], digest: str) -> Optional[list]:
    """성공 시 요약 줄 리스트, 비활성/실패 시 None (예외를 밖으로 던지지 않음)."""
    ai_cfg = ai_cfg or {}
    if not ai_cfg.get("enabled", False):
        return None
    api_key = _resolve_api_key(ai_cfg)
    if not api_key:
        print("   [AI 요약] API 키가 없어 건너뜀 (config.json ai.api_key 또는 ANTHROPIC_API_KEY)")
        return None

    payload = {
        "model": ai_cfg.get("model", DEFAULT_MODEL),
        "max_tokens": int(ai_cfg.get("max_tokens", 600)),
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": "다음 로그 집계 결과를 요약해 주세요.\n\n" + digest}],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=int(ai_cfg.get("timeout_sec", DEFAULT_TIMEOUT))) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
        lines = parse_summary(text)
        if not lines:
            print("   [AI 요약] 빈 응답 — 건너뜀")
            return None
        print("   [AI 요약] 생성 완료")
        return lines
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        print(f"   [AI 요약] API 오류 {e.code}: {detail} — 기존 리포트만 발송")
    except Exception as e:
        print(f"   [AI 요약] 호출 실패 ({e}) — 기존 리포트만 발송")
    return None
