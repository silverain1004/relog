"""수시 분석(--today / --from / --to) 기간 해석 테스트."""
from datetime import date

import pytest

from cli_common import build_arg_parser, is_auto_mode, resolve_period_from_args
from period_utils import get_output_subdir, parse_date_range


def _resolve(*argv):
    args = build_arg_parser("t").parse_args(list(argv))
    return args, resolve_period_from_args(args)


def test_single_day():
    _, p = _resolve("--from", "2026-10-29", "--to", "2026-10-29")
    assert p["start"] == p["end"] == date(2026, 10, 29)
    assert p["key"] == "D20261029"
    assert p["label"] == "2026-10-29 수시 분석"
    assert get_output_subdir(p["period_type"]) == "adhoc"


def test_range():
    _, p = _resolve("--from", "2026-10-26", "--to", "2026-10-29")
    assert p["key"] == "D20261026-20261029"
    assert p["label"] == "2026-10-26 ~ 2026-10-29 수시 분석"


def test_from_without_to_runs_until_today():
    _, p = _resolve("--from", date.today().isoformat())
    assert p["start"] == p["end"] == date.today()


def test_today_is_non_interactive():
    args, p = _resolve("--today")
    assert p["start"] == p["end"] == date.today()
    assert is_auto_mode(args)


def test_adhoc_reports_go_to_own_folder():
    # ZIP은 폴더 안에서 key 포함 여부로 파일을 고름 — 월별 key(202610)는 D20261029 안에도
    # 들어 있으므로, 수시 리포트는 반드시 별도 폴더(adhoc)에 저장돼야 섞이지 않음
    p = parse_date_range("2026-10-29", "2026-10-29")
    assert get_output_subdir(p["period_type"]) not in ("weekly", "monthly")


@pytest.mark.parametrize("argv", [
    ("--from", "2026-10-30", "--to", "2026-10-29"),
    ("--to", "2026-10-29"),
    ("--from", "2026/10/29"),
])
def test_invalid_input(argv):
    with pytest.raises(ValueError):
        _resolve(*argv)


def test_today_and_auto_are_exclusive():
    with pytest.raises(SystemExit):
        build_arg_parser("t").parse_args(["--today", "--auto", "weekly"])


def test_auto_weekly_unchanged():
    _, p = _resolve("--auto", "weekly", "--date", "2026-11-02")
    assert p["key"] == "2026W44"
    assert get_output_subdir(p["period_type"]) == "weekly"
