"""데이터베이스 모델 (구조와 관계는 docs/ARCHITECTURE.md 참고)."""
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MeetingStatus:
    SCHEDULED = "scheduled"  # 예정
    READY = "ready"  # 준비 완료 (브리핑 생성 완료)
    COMPLETED = "completed"  # 진행 완료
    ALL = (SCHEDULED, READY, COMPLETED)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    job_title: Mapped[str | None] = mapped_column(String(100))  # 직무 (예: 백엔드 개발)
    role: Mapped[str] = mapped_column(String(20), default="member")  # member | admin
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    meetings: Mapped[list["Meeting"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(Text, default="")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(255))
    online_url: Mapped[str | None] = mapped_column(String(500))
    agenda: Mapped[str] = mapped_column(Text, default="")  # 줄바꿈 구분 안건 목록
    status: Mapped[str] = mapped_column(String(20), default=MeetingStatus.SCHEDULED, index=True)
    # 향후 Google Calendar 연동용 (외부 일정 ID)
    external_calendar_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="meetings")
    participants: Mapped[list["Participant"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", order_by="Participant.id"
    )
    materials: Mapped[list["MeetingMaterial"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", order_by="MeetingMaterial.id"
    )
    briefings: Mapped[list["Briefing"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    glossary: Mapped[list["GlossaryTerm"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", order_by="GlossaryTerm.id"
    )
    email_jobs: Mapped[list["EmailJob"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    email_logs: Mapped[list["EmailLog"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    questions: Mapped[list["Question"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    result: Mapped["MeetingResult | None"] = relationship(back_populates="meeting", cascade="all, delete-orphan", uselist=False)
    tasks: Mapped[list["Task"]] = relationship(back_populates="meeting", cascade="all, delete-orphan", order_by="Task.id")

    @property
    def agenda_items(self) -> list[str]:
        return [line.strip(" -•\t") for line in (self.agenda or "").splitlines() if line.strip(" -•\t")]


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("meeting_id", "email", name="uq_participant_meeting_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(100), default="")  # 참석자 역할/직무 (예: 개발 담당자)
    responsibility: Mapped[str] = mapped_column(Text, default="")  # 담당 업무
    # 로그인 없이 개인 브리핑 페이지에 접근하기 위한 추측 불가능한 토큰
    access_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="participants")


class MeetingMaterial(Base):
    __tablename__ = "meeting_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(10))  # pdf | docx | pptx | txt
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="processed")  # processed | failed
    error: Mapped[str | None] = mapped_column(Text)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    # [{"loc": "p.1", "text": "..."}] — 출처 표시용 위치 정보
    segments: Mapped[list] = mapped_column(JSON, default=list)
    title: Mapped[str | None] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    summary_source: Mapped[str | None] = mapped_column(String(20))  # openai | mock
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="materials")


class Briefing(Base):
    """participant_id 가 NULL 이면 회의 공통 브리핑, 값이 있으면 참석자별 브리핑."""

    __tablename__ = "briefings"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(20))  # openai | mock
    model: Mapped[str | None] = mapped_column(String(100))
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="briefings")
    participant: Mapped[Participant | None] = relationship()


class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    term: Mapped[str] = mapped_column(String(200))
    easy_explanation: Mapped[str] = mapped_column(Text, default="")
    work_meaning: Mapped[str] = mapped_column(Text, default="")
    related_concepts: Mapped[list] = mapped_column(JSON, default=list)
    context: Mapped[str] = mapped_column(Text, default="")  # 자료 속 사용 문맥
    source_ref: Mapped[str | None] = mapped_column(String(300))  # 파일명 + 위치
    why_important: Mapped[str] = mapped_column(Text, default="")
    is_uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20))  # openai | mock
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="glossary")


class EmailJob(Base):
    """이메일 발송 작업. 즉시 발송도 동일한 작업 단위로 처리하여 중복 발송을 막는다."""

    __tablename__ = "email_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    participant_ids: Mapped[list] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String(20))  # now | scheduled | before_meeting
    minutes_before: Mapped[int | None] = mapped_column(Integer)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # pending → processing → done | partial | failed ,  pending → cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    meeting: Mapped[Meeting] = relationship(back_populates="email_jobs")


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int | None] = mapped_column(ForeignKey("participants.id", ondelete="SET NULL"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("email_jobs.id", ondelete="SET NULL"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), index=True)
    recipient: Mapped[str] = mapped_column(String(255))
    email_type: Mapped[str] = mapped_column(String(30), default="briefing")  # briefing | task_reminder
    subject: Mapped[str] = mapped_column(String(300))
    body_html: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20))  # sent | failed | retrying
    provider: Mapped[str] = mapped_column(String(20))  # resend | mock
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="email_logs")
    participant: Mapped[Participant | None] = relationship()


class Question(Base):
    """회의 자료 기반 AI 질의응답 기록."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    # grounded: materials(자료 근거) | partial(일부 근거 + 일반 지식) | none(자료에서 근거를 찾지 못함)
    grounded: Mapped[str] = mapped_column(String(20))
    # [{"file": "a.pdf", "loc": "p.3", "quote": "..."}]
    citations: Mapped[list] = mapped_column(JSON, default=list)
    general_knowledge: Mapped[str | None] = mapped_column(Text)  # 자료가 아닌 일반 지식에 기반한 보충 설명
    source: Mapped[str] = mapped_column(String(20))  # openai | mock
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="questions")


class MeetingResult(Base):
    """회의 종료 후 결과. AI 분석 결과(draft)를 사용자가 확인·수정 후 확정(confirmed)한다."""

    __tablename__ = "meeting_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), unique=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")  # 입력한 회의 내용 / 회의록 파일 추출 텍스트
    source_filename: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text, default="")
    decisions: Mapped[list] = mapped_column(JSON, default=list)  # 최종 결정 사항
    undecided: Mapped[list] = mapped_column(JSON, default=list)  # 미결정 사항
    further_discussion: Mapped[list] = mapped_column(JSON, default=list)  # 추가 논의 필요
    draft_tasks: Mapped[list] = mapped_column(JSON, default=list)  # AI가 추출한 업무 후보 (확정 전)
    source: Mapped[str | None] = mapped_column(String(20))  # openai | mock
    model: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | confirmed
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="result")


class TaskStatus:
    TODO = "todo"  # 대기
    IN_PROGRESS = "in_progress"  # 진행 중
    DONE = "done"  # 완료
    ALL = (TODO, IN_PROGRESS, DONE)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    assignee_participant_id: Mapped[int | None] = mapped_column(ForeignKey("participants.id", ondelete="SET NULL"), index=True)
    assignee_name: Mapped[str] = mapped_column(String(100), default="")
    assignee_email: Mapped[str | None] = mapped_column(String(255), index=True)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium")  # high | medium | low
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.TODO, index=True)
    from_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="tasks")
