"""기간 계산 유틸 (ISO 주차 / 월별 / 수시 날짜 구간).

Python 3.6 호환 유지 필수 — WEB1 서버(Linux)가 3.6.8이라
`X | None` 표기, `tuple[...]` 제네릭, `date.fromisocalendar`를 쓰면 안 됨.
"""
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple
import calendar

def get_iso_week_range(year: int, week: int) -> Tuple[date, date]:
    # date.fromisocalendar는 3.8+ — ISO 1주는 1월 4일이 포함된 주
    jan4 = date(year, 1, 4)
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    start = week1_monday + timedelta(weeks=week - 1)
    end = start + timedelta(days=6)
    return start, end


def get_month_range(year: int, month: int) -> Tuple[date, date]:
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)
    return start, end


def iter_dates(start: date, end: date) -> List[date]:
    dates = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def get_period_range(period_type: str, year: int, week: int = None, month: int = None) -> Tuple[date, date]:
    if period_type == "weekly":
        return get_iso_week_range(year, week)
    return get_month_range(year, month)


def get_period_key(period_type: str, year: int, week: int = None, month: int = None) -> str:
    if period_type == "weekly":
        return f"{year}W{int(week):02d}"
    return f"{year}{int(month):02d}"


def get_output_subdir(period_type: str) -> str:
    if period_type == "range":
        return "adhoc"
    return "weekly" if period_type == "weekly" else "monthly"


def parse_date_range(start_str: str, end_str: Optional[str] = None) -> dict:
    """수시 분석 — 원하는 날짜(또는 날짜 구간)만 분석. 장애 직후 수동 실행용.

    end_str을 생략하면 오늘까지. key는 'D' 접두어로 주별·월별과 구분하고,
    리포트는 별도 폴더(adhoc)에 저장 — ZIP은 폴더 안에서 key 포함 여부로 파일을
    고르는데, 월별 key(202610)가 D20261029 안에도 들어 있어 같은 폴더면 섞이기 때문.
    """
    try:
        start = datetime.strptime(start_str.strip(), "%Y-%m-%d").date()
        end = datetime.strptime(end_str.strip(), "%Y-%m-%d").date() if end_str else date.today()
    except ValueError:
        raise ValueError("날짜는 YYYY-MM-DD 형식으로 입력해주세요. (예: 2026-10-29)")
    if end < start:
        raise ValueError(f"종료일({end})이 시작일({start})보다 앞섭니다.")
    s, e = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    key = f"D{s}" if start == end else f"D{s}-{e}"
    range_str = start.isoformat() if start == end else f"{start.isoformat()} ~ {end.isoformat()}"
    return {
        "period_type": "range",
        "year": start.year,
        "week": None,
        "month": None,
        "start": start,
        "end": end,
        "key": key,
        "label": f"{range_str} 수시 분석",
    }


def format_period_label(period_type: str, start: date, end: date, year: int,
                        week: int = None, month: int = None) -> str:
    range_str = f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}"
    if period_type == "weekly":
        return f"{year}년 {int(week)}주 ({range_str})"
    return f"{year}년 {int(month):02d}월 ({range_str})"


def parse_weekly_from_date(date_str: str) -> dict:
    """날짜 하나만 입력하면 해당 ISO 주 전체를 반환."""
    d = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    iso = d.isocalendar()
    year, week = iso[0], iso[1]
    start, end = get_iso_week_range(year, week)
    return {
        "period_type": "weekly",
        "year": year,
        "week": week,
        "month": None,
        "start": start,
        "end": end,
        "key": get_period_key("weekly", year, week=week),
        "label": format_period_label("weekly", start, end, year, week=week),
        "anchor_date": d.isoformat(),
    }


def parse_period_input(period_type: str, year_str: str, value_str: str) -> dict:
    year = int(year_str)
    if period_type == "weekly":
        week = int(value_str)
        start, end = get_iso_week_range(year, week)
        return {
            "period_type": period_type,
            "year": year,
            "week": week,
            "month": None,
            "start": start,
            "end": end,
            "key": get_period_key(period_type, year, week=week),
            "label": format_period_label(period_type, start, end, year, week=week),
        }
    month = int(value_str)
    start, end = get_month_range(year, month)
    return {
        "period_type": period_type,
        "year": year,
        "week": None,
        "month": month,
        "start": start,
        "end": end,
        "key": get_period_key(period_type, year, month=month),
        "label": format_period_label(period_type, start, end, year, month=month),
    }


def prompt_period() -> Optional[dict]:
    """Win/Linux 공통 — 주별은 날짜 입력, 월별은 연도+월 입력, 수시는 날짜 구간 입력."""
    print("리포트 유형: 1) 주별  2) 월별  3) 수시(날짜 지정)")
    choice = input("선택 (1, 2, 3): ").strip()
    if choice not in ("1", "2", "3"):
        print("[오류] 1, 2, 3 중 하나를 입력해주세요.")
        return None

    if choice == "3":
        print("\n[수시] 분석할 날짜를 입력하세요. 종료일을 비우면 시작일 하루만 분석합니다.")
        start_str = input("시작일 (YYYY-MM-DD, 비우면 오늘): ").strip() or date.today().isoformat()
        end_str = input("종료일 (YYYY-MM-DD, 비우면 시작일과 같음): ").strip() or start_str
        try:
            period = parse_date_range(start_str, end_str)
            print(f"  → {period['label']}")
            return period
        except ValueError as e:
            print(f"[오류] {e}")
            return None

    if choice == "1":
        print("\n[주별] 조회할 주에 포함된 아무 날짜나 입력하세요.")
        print("       (ISO 주차를 직접 계산할 필요 없습니다)")
        date_str = input("날짜 (YYYY-MM-DD, 예: 2026-06-10): ").strip()
        if not date_str:
            return None
        try:
            period = parse_weekly_from_date(date_str)
            print(f"  → {period['label']}")
            return period
        except ValueError:
            print("[오류] 날짜 형식이 올바르지 않습니다. (예: 2026-06-10)")
            return None

    year = input("조회 연도 (YYYY): ").strip()
    month = input("조회 월 (MM): ").strip()
    if not year or not month:
        return None
    return parse_period_input("monthly", year, month)


def get_auto_weekly_period(reference: Optional[date] = None) -> dict:
    """직전 완료된 ISO 주 (월~일). reference 기준 이번 주 월요일에서 7일 전."""
    ref = reference or date.today()
    this_monday = ref - timedelta(days=ref.weekday())
    prev_monday = this_monday - timedelta(days=7)
    return parse_weekly_from_date(prev_monday.isoformat())


def get_auto_monthly_period(reference: Optional[date] = None) -> dict:
    """직전 완료된 달."""
    ref = reference or date.today()
    first_of_month = ref.replace(day=1)
    last_prev = first_of_month - timedelta(days=1)
    return parse_period_input("monthly", str(last_prev.year), str(last_prev.month))


def resolve_auto_period(auto_type: str, reference: Optional[date] = None) -> dict:
    if auto_type == "weekly":
        return get_auto_weekly_period(reference)
    if auto_type == "monthly":
        return get_auto_monthly_period(reference)
    raise ValueError(f"지원하지 않는 auto_type: {auto_type}")
