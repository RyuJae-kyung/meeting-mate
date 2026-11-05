"""회의록 속 한국어 마감일 표현 해석 ('11월 10일', '11/10', '다음 주 금요일', '내일' 등)."""
import re
from datetime import date, timedelta

WEEKDAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}

_PATTERNS = [
    r"\d{4}[-./]\s*\d{1,2}[-./]\s*\d{1,2}",
    r"\d{1,2}\s*월\s*\d{1,2}\s*일",
    r"(?<![\d.])\d{1,2}/\d{1,2}(?![\d/])",
    r"(?:이번\s*주|금주|다음\s*주|차주|다다음\s*주)\s*[월화수목금토일]요일",
    r"[월화수목금토일]요일",
    r"내일|모레|오늘|이번\s*주\s*(?:내|중)|이번\s*주말|다음\s*주\s*(?:내|중)|월말|이번\s*달\s*(?:말|내)",
]
DUE_RE = re.compile("|".join(f"(?:{p})" for p in _PATTERNS))


def _safe(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_due(expr: str, ref: date) -> date | None:
    """표현 하나를 기준일(ref, 보통 회의일) 기준 날짜로 변환. 해석 불가하면 None."""
    e = re.sub(r"\s+", "", expr)
    if m := re.fullmatch(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", e):
        return _safe(int(m[1]), int(m[2]), int(m[3]))
    if m := re.fullmatch(r"(\d{1,2})월(\d{1,2})일", e) or re.fullmatch(r"(\d{1,2})/(\d{1,2})", e):
        d = _safe(ref.year, int(m[1]), int(m[2]))
        if d and d < ref - timedelta(days=30):  # 연말 회의에서 '1월 5일' → 다음 해
            d = _safe(ref.year + 1, int(m[1]), int(m[2]))
        return d
    if e == "오늘":
        return ref
    if e == "내일":
        return ref + timedelta(days=1)
    if e == "모레":
        return ref + timedelta(days=2)
    if m := re.fullmatch(r"(이번주|금주|다음주|차주|다다음주)?([월화수목금토일])요일", e):
        week_offset = {None: 0, "이번주": 0, "금주": 0, "다음주": 1, "차주": 1, "다다음주": 2}[m[1]]
        monday = ref - timedelta(days=ref.weekday())
        d = monday + timedelta(weeks=week_offset, days=WEEKDAYS[m[2]])
        if m[1] is None and d < ref:  # 그냥 '금요일' 인데 이미 지났으면 다음 주
            d += timedelta(weeks=1)
        return d
    if e in ("이번주내", "이번주중"):
        return ref - timedelta(days=ref.weekday()) + timedelta(days=4)
    if e == "이번주말":
        return ref - timedelta(days=ref.weekday()) + timedelta(days=6)
    if e in ("다음주내", "다음주중"):
        return ref - timedelta(days=ref.weekday()) + timedelta(days=11)
    if e in ("월말", "이번달말", "이번달내"):
        nxt = date(ref.year + (ref.month == 12), ref.month % 12 + 1, 1)
        return nxt - timedelta(days=1)
    return None


def find_due(text: str, ref: date) -> tuple[date | None, str | None]:
    m = DUE_RE.search(text)
    if not m:
        return None, None
    return parse_due(m.group(0), ref), m.group(0)
