"""회의 결과 분석(AI 초안) → 사용자 확인·수정 → 확정(후속 업무 생성)."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Meeting, MeetingResult, MeetingStatus, Participant, Task, User
from ..schemas import ResultAnalysis, ResultConfirmIn, TaskConfirmIn
from .ai import get_ai_provider
from .briefing_service import build_ctx


def match_participant(meeting: Meeting, name: str) -> Participant | None:
    name = (name or "").strip()
    if not name:
        return None
    exact = [p for p in meeting.participants if p.name == name]
    if exact:
        return exact[0]
    # '김개발님', '개발자 김개발' 처럼 이름이 포함된 경우
    partial = [p for p in meeting.participants if p.name and (p.name in name or name in p.name)]
    return partial[0] if len(partial) == 1 else None


def analyze(db: Session, meeting: Meeting, raw_text: str, source_filename: str | None) -> MeetingResult:
    provider = get_ai_provider()
    ref_date = meeting.start_at.astimezone(ZoneInfo(get_settings().DISPLAY_TIMEZONE)).date()
    data = ResultAnalysis.model_validate(provider.analyze_result(build_ctx(meeting), raw_text, ref_date))
    drafts = []
    for t in data.tasks:
        p = match_participant(meeting, t.assignee_name)
        t.assignee_participant_id = p.id if p else None
        if p:
            t.assignee_name = p.name
        elif t.assignee_name:
            t.uncertain = True  # 참석자 목록에 없는 담당자
        drafts.append(t.model_dump(mode="json"))
    r = meeting.result or MeetingResult(meeting_id=meeting.id)
    if r.status == "confirmed":
        # 이미 확정된 결과를 재분석하면 다시 초안 상태로 (기존 업무는 그대로 유지)
        r.confirmed_at = None
    r.raw_text, r.source_filename = raw_text, source_filename
    r.summary, r.decisions, r.undecided, r.further_discussion = data.summary, data.decisions, data.undecided, data.further_discussion
    r.draft_tasks, r.source, r.model, r.status = drafts, provider.name, provider.model, "draft"
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def apply_assignee(meeting: Meeting, task: Task, participant_id: int | None, name: str) -> None:
    if participant_id is not None:
        p = next((x for x in meeting.participants if x.id == participant_id), None)
        if p is None:
            raise HTTPException(422, "담당자는 이 회의의 참석자여야 합니다.")
        task.assignee_participant_id, task.assignee_name, task.assignee_email = p.id, p.name, p.email
        return
    p = match_participant(meeting, name)
    if p:
        task.assignee_participant_id, task.assignee_name, task.assignee_email = p.id, p.name, p.email
    else:  # 참석자가 아닌 담당자 (이메일 알림 불가)
        task.assignee_participant_id, task.assignee_name, task.assignee_email = None, (name or "").strip(), None


def new_task(meeting: Meeting, user: User, data: TaskConfirmIn, from_ai: bool) -> Task:
    t = Task(meeting_id=meeting.id, created_by=user.id, title=data.title.strip(), description=data.description,
             due_date=data.due_date, priority=data.priority, reminder_enabled=data.reminder_enabled, from_ai=from_ai)
    apply_assignee(meeting, t, data.assignee_participant_id, data.assignee_name)
    return t


def confirm(db: Session, meeting: Meeting, user: User, body: ResultConfirmIn) -> tuple[MeetingResult, list[Task]]:
    r = meeting.result
    if r is None:
        r = MeetingResult(meeting_id=meeting.id, raw_text="")
        db.add(r)
    clean = lambda xs: [x.strip() for x in xs if x.strip()]  # noqa: E731
    r.summary, r.decisions = body.summary.strip(), clean(body.decisions)
    r.undecided, r.further_discussion = clean(body.undecided), clean(body.further_discussion)
    r.status, r.confirmed_at, r.draft_tasks = "confirmed", datetime.now(timezone.utc), []
    tasks = [new_task(meeting, user, t, from_ai=True) for t in body.tasks]
    db.add_all(tasks)
    if body.mark_completed:
        meeting.status = MeetingStatus.COMPLETED
    db.commit()
    for t in tasks:
        db.refresh(t)
    db.refresh(r)
    return r, tasks
