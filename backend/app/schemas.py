"""API 요청/응답 스키마 및 AI 결과 검증 스키마."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    job_title: str | None = Field(default=None, max_length=100)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: int
    email: str
    name: str
    job_title: str | None
    role: str
    email_notifications: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    job_title: str | None = Field(default=None, max_length=100)
    email_notifications: bool | None = None


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ---------- Participants ----------
class ParticipantIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    role: str = Field(default="", max_length=100)
    responsibility: str = Field(default="", max_length=2000)

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.lower()


class ParticipantOut(ORM):
    id: int
    meeting_id: int
    name: str
    email: str
    role: str
    responsibility: str
    created_at: datetime


class ParticipantOwnerOut(ParticipantOut):
    access_token: str | None = None  # 회의 생성자에게만 노출 (개인 브리핑 링크용)


# ---------- Meetings ----------
class MeetingBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(default="", max_length=5000)
    start_at: datetime
    end_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    online_url: str | None = Field(default=None, max_length=500)
    agenda: str = Field(default="", max_length=10000)

    @field_validator("start_at", "end_at")
    @classmethod
    def tz_required(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("시간대 정보가 포함된 ISO 8601 형식이어야 합니다 (예: 2026-11-10T14:00:00+09:00).")
        return v


class MeetingCreateIn(MeetingBase):
    participants: list[ParticipantIn] = Field(default_factory=list, max_length=100)


class MeetingUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    purpose: str | None = Field(default=None, max_length=5000)
    start_at: datetime | None = None
    end_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    online_url: str | None = Field(default=None, max_length=500)
    agenda: str | None = Field(default=None, max_length=10000)


class MeetingStatusIn(BaseModel):
    status: Literal["scheduled", "ready", "completed"]


class MaterialBrief(ORM):
    id: int
    original_filename: str
    file_type: str
    size_bytes: int
    status: str
    error: str | None
    title: str | None
    summary: str | None
    summary_source: str | None
    keywords: list
    uploaded_at: datetime


class MaterialDetail(MaterialBrief):
    extracted_text: str
    segments: list


class MeetingListItem(ORM):
    id: int
    title: str
    purpose: str
    start_at: datetime
    end_at: datetime | None
    location: str | None
    online_url: str | None
    status: str
    owner_id: int
    participant_count: int = 0
    material_count: int = 0
    has_briefing: bool = False


class MeetingDetail(MeetingListItem):
    agenda: str
    agenda_items: list[str]
    created_at: datetime
    updated_at: datetime
    can_edit: bool
    owner_name: str
    participants: list[ParticipantOwnerOut]
    materials: list[MaterialBrief]


# ---------- Briefing content (AI 출력 검증) ----------
Basis = Literal["fact", "inference", "uncertain"]


class BriefingItem(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    # fact: 회의 정보/자료에 명시된 사실, inference: AI 추론, uncertain: 불확실·확인 필요
    basis: Basis = "inference"
    source: str | None = Field(default=None, max_length=300)


class GeneralBriefingContent(BaseModel):
    purpose_summary: list[BriefingItem] = Field(default_factory=list)
    agenda_items: list[BriefingItem] = Field(default_factory=list)
    expected_discussions: list[BriefingItem] = Field(default_factory=list)
    pre_questions: list[BriefingItem] = Field(default_factory=list)
    checklist: list[BriefingItem] = Field(default_factory=list)
    issues: list[BriefingItem] = Field(default_factory=list)
    material_summaries: list[BriefingItem] = Field(default_factory=list)


class PersonalBriefingContent(BaseModel):
    focus_summary: str = Field(default="", max_length=2000)
    key_agenda: list[BriefingItem] = Field(default_factory=list)
    materials_to_review: list[BriefingItem] = Field(default_factory=list)
    expected_questions: list[BriefingItem] = Field(default_factory=list)
    preparation: list[BriefingItem] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)


class GlossaryItemContent(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    easy_explanation: str = ""
    work_meaning: str = ""
    related_concepts: list[str] = Field(default_factory=list)
    context: str = ""
    source_ref: str | None = None
    why_important: str = ""
    is_uncertain: bool = False


class BriefingOut(ORM):
    id: int
    meeting_id: int
    participant_id: int | None
    content: dict
    source: str
    model: str | None
    is_edited: bool
    created_at: datetime
    updated_at: datetime


class BriefingUpdateIn(BaseModel):
    content: dict


class ParticipantBriefingOut(BaseModel):
    participant: ParticipantOwnerOut
    briefing: BriefingOut | None


class GlossaryOut(ORM):
    id: int
    meeting_id: int
    term: str
    easy_explanation: str
    work_meaning: str
    related_concepts: list
    context: str
    source_ref: str | None
    why_important: str
    is_uncertain: bool
    source: str
    is_edited: bool


class GlossaryUpdateIn(BaseModel):
    term: str | None = Field(default=None, min_length=1, max_length=200)
    easy_explanation: str | None = None
    work_meaning: str | None = None
    related_concepts: list[str] | None = None
    why_important: str | None = None


class GenerateResult(BaseModel):
    source: str
    general_briefing_id: int
    glossary_count: int
    participant_briefing_count: int
    meeting_status: str
    warnings: list[str] = Field(default_factory=list)


# ---------- Email ----------
class EmailPreviewIn(BaseModel):
    participant_id: int


class EmailPreviewOut(BaseModel):
    to: str
    subject: str
    html: str
    provider: str


class EmailSendIn(BaseModel):
    participant_ids: list[int] = Field(min_length=1, max_length=100)
    mode: Literal["now", "scheduled", "before_meeting"]
    scheduled_at: datetime | None = None
    minutes_before: int | None = Field(default=None, ge=5, le=60 * 24 * 14)
    confirm: bool = False  # 사용자 확인 없이는 발송하지 않음


class EmailLogOut(ORM):
    id: int
    meeting_id: int
    participant_id: int | None
    job_id: int | None
    recipient: str
    email_type: str
    subject: str
    status: str
    provider: str
    provider_message_id: str | None
    error: str | None
    attempts: int
    sent_at: datetime | None
    created_at: datetime


class EmailLogDetail(EmailLogOut):
    body_html: str


class EmailJobOut(ORM):
    id: int
    meeting_id: int
    participant_ids: list
    mode: str
    minutes_before: int | None
    scheduled_at: datetime
    status: str
    error: str | None
    created_at: datetime
    processed_at: datetime | None


class EmailSendOut(BaseModel):
    job: EmailJobOut
    logs: list[EmailLogOut]


# ---------- Public / Dashboard ----------
class PublicBriefingOut(BaseModel):
    meeting_title: str
    meeting_purpose: str
    start_at: datetime
    end_at: datetime | None
    location: str | None
    online_url: str | None
    agenda_items: list[str]
    participant_name: str
    participant_role: str
    participant_responsibility: str
    personal: BriefingOut | None
    checklist: list[dict]
    glossary: list[GlossaryOut]


class DashboardOut(BaseModel):
    upcoming: list[MeetingListItem]
    recent: list[MeetingListItem]
    ready: list[MeetingListItem]
    recent_emails: list[EmailLogOut]
    pending_email_jobs: list[EmailJobOut]
    counts: dict


class SystemStatusOut(BaseModel):
    ai_provider: str
    ai_model: str | None
    email_provider: str
    email_from: str
    scheduler_enabled: bool
    scheduler_interval_seconds: int
    calendar: str
    max_upload_mb: int
    allowed_file_types: list[str]
