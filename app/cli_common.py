"""Win/Linux 공통 CLI 인자 처리. Python 3.6 호환 유지 (WEB1 서버가 3.6.8)."""
import argparse
from datetime import datetime
from typing import Optional

from period_utils import prompt_period, resolve_auto_period


def build_arg_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--auto",
        choices=["weekly", "monthly"],
        help="자동 기간 분석 (weekly=직전 ISO 주, monthly=직전 월)",
    )
    parser.add_argument(
        "--date",
        help="--auto weekly 시 기준 날짜 (YYYY-MM-DD, 미지정 시 오늘)",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="메일 발송 생략",
    )
    parser.add_argument(
        "--test-email",
        action="store_true",
        help="config.json의 실제 수신자 목록 대신 발신 계정(from_addr) 본인에게만 발송 (테스트용)",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="AI 요약(Claude API) 생략",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="설정 파일 경로 (기본: 실행 폴더의 config.json)",
    )
    return parser


def resolve_period_from_args(args) -> Optional[dict]:
    if args.auto:
        ref = None
        if args.date:
            ref = datetime.strptime(args.date, "%Y-%m-%d").date()
        return resolve_auto_period(args.auto, ref)
    return prompt_period()


def is_auto_mode(args) -> bool:
    return bool(args.auto)
