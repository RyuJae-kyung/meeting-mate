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
