"""캘린더 연동 확장 지점.

초기 버전은 자체 일정(Meeting.start_at/end_at)만 사용한다.
Google Calendar 연동 시 CalendarProvider 를 구현하고 Meeting.external_calendar_id 에 외부 일정 ID를 저장한다.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class CalendarEvent:
    external_id: str
    title: str
    start_at: datetime
    end_at: datetime | None
    location: str | None
    attendees: list[str]


class CalendarProvider(Protocol):
    name: str

    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]: ...  # 일정 불러오기

    def create_event(self, event: CalendarEvent) -> str: ...  # 캘린더에 회의 등록 → external_id

    def get_event(self, external_id: str) -> CalendarEvent | None: ...  # 변경 감지용 조회


def get_calendar_status() -> str:
    return "not_connected"  # Google Calendar 연동은 다음 단계에서 구현


def meeting_to_ics(meeting, frontend_url: str) -> str:
    """표준 iCalendar(.ics). Google Calendar·Outlook·Apple 캘린더에서 가져오기 가능."""
    from datetime import timedelta, timezone

    def esc(v: str) -> str:
        bs = chr(92)
        return (v or "").replace(bs, bs * 2).replace(";", bs + ";").replace(",", bs + ",").replace("\n", bs + "n")

    def fmt(dt) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    end = meeting.end_at or meeting.start_at + timedelta(hours=1)
    url = f"{frontend_url.rstrip('/')}/meetings/{meeting.id}"
    desc = f"{meeting.purpose}\n\n안건:\n" + "\n".join(f"- {a}" for a in meeting.agenda_items) + f"\n\n{url}"
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Meeting Mate//KO", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "BEGIN:VEVENT", f"UID:meeting-{meeting.id}@meeting-mate", f"DTSTAMP:{fmt(meeting.updated_at)}",
        f"DTSTART:{fmt(meeting.start_at)}", f"DTEND:{fmt(end)}", f"SUMMARY:{esc(meeting.title)}",
        f"DESCRIPTION:{esc(desc)}", f"LOCATION:{esc(meeting.location or meeting.online_url or '')}", f"URL:{url}",
        *[f"ATTENDEE;CN={esc(p.name)}:mailto:{p.email}" for p in meeting.participants],
        "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
