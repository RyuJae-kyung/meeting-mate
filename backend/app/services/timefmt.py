from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import get_settings

WEEKDAYS = "월화수목금토일"


def fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    local = dt.astimezone(ZoneInfo(get_settings().DISPLAY_TIMEZONE))
    return f"{local:%Y년 %m월 %d일} ({WEEKDAYS[local.weekday()]}) {local:%H:%M}"


def fmt_range(start: datetime, end: datetime | None) -> str:
    s = fmt_dt(start)
    if end is None:
        return s
    tz = ZoneInfo(get_settings().DISPLAY_TIMEZONE)
    return f"{s} ~ {end.astimezone(tz):%H:%M}"
