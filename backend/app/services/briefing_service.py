"""브리핑·용어·참석자별 브리핑 생성 오케스트레이션."""
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Briefing, GlossaryTerm, Meeting, MeetingStatus, Participant
from .ai import AIError, MaterialCtx, MeetingCtx, ParticipantCtx, get_ai_provider
from .timefmt import fmt_range

log = logging.getLogger(__name__)


def build_ctx(meeting: Meeting) -> MeetingCtx:
    return MeetingCtx(
        title=meeting.title,
        purpose=meeting.purpose or "",
        agenda_items=meeting.agenda_items,
        start_at_text=fmt_range(meeting.start_at, meeting.end_at),
        location=meeting.location or meeting.online_url,
        materials=[
            MaterialCtx(filename=m.original_filename, title=m.title, segments=m.segments or [], keywords=m.keywords or [])
            for m in meeting.materials
            if m.status == "processed"
        ],
        participants=[ParticipantCtx(p.name, p.role, p.responsibility) for p in meeting.participants],
    )


def _upsert_personal(db: Session, meeting: Meeting, participant: Participant, ctx: MeetingCtx, terms: list[str], provider) -> Briefing:
    content = provider.personal_briefing(ctx, ParticipantCtx(participant.name, participant.role, participant.responsibility), terms)
    existing = db.scalar(select(Briefing).where(Briefing.participant_id == participant.id))
    if existing:
        existing.content, existing.source, existing.model, existing.is_edited = content, provider.name, provider.model, False
        return existing
    b = Briefing(meeting_id=meeting.id, participant_id=participant.id, content=content, source=provider.name, model=provider.model)
    db.add(b)
    return b


def generate_all(db: Session, meeting: Meeting) -> dict:
    """공통 브리핑 → 용어 → 참석자별 브리핑 순서로 생성.

    AI 호출이 모두 끝난 뒤에 한 번에 커밋하므로, 중간에 실패하면 기존 결과가 그대로 유지된다.
    """
    provider = get_ai_provider()
    ctx = build_ctx(meeting)
    warnings: list[str] = []
    if not ctx.materials:
        warnings.append("분석 가능한 회의 자료가 없어 회의 정보만으로 브리핑을 생성했습니다.")
    if not meeting.participants:
        warnings.append("참석자가 없어 참석자별 브리핑은 생성되지 않았습니다.")

    general = provider.generate_briefing(ctx)
    glossary = provider.extract_glossary(ctx)
    terms = [g["term"] for g in glossary]
    personal_contents = []
    for p in meeting.participants:
        personal_contents.append((p, provider.personal_briefing(ctx, ParticipantCtx(p.name, p.role, p.responsibility), terms)))

    # ---- 저장 (AI 결과가 모두 준비된 뒤) ----
    db.execute(delete(Briefing).where(Briefing.meeting_id == meeting.id))
    db.execute(delete(GlossaryTerm).where(GlossaryTerm.meeting_id == meeting.id))
    gb = Briefing(meeting_id=meeting.id, participant_id=None, content=general, source=provider.name, model=provider.model)
    db.add(gb)
    for g in glossary:
        db.add(GlossaryTerm(meeting_id=meeting.id, source=provider.name, **g))
    for p, content in personal_contents:
        db.add(Briefing(meeting_id=meeting.id, participant_id=p.id, content=content, source=provider.name, model=provider.model))
    if meeting.status == MeetingStatus.SCHEDULED:
        meeting.status = MeetingStatus.READY
    db.commit()
    db.refresh(gb)
    return {
        "source": provider.name,
        "general_briefing_id": gb.id,
        "glossary_count": len(glossary),
        "participant_briefing_count": len(personal_contents),
        "meeting_status": meeting.status,
        "warnings": warnings,
    }


def regenerate_personal(db: Session, meeting: Meeting, participant: Participant) -> Briefing:
    provider = get_ai_provider()
    ctx = build_ctx(meeting)
    terms = [g.term for g in meeting.glossary]
    b = _upsert_personal(db, meeting, participant, ctx, terms, provider)
    db.commit()
    db.refresh(b)
    return b


__all__ = ["AIError", "build_ctx", "generate_all", "regenerate_personal"]
