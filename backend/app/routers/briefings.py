from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import can_edit, get_current_user, get_meeting_for_edit, get_meeting_for_view
from ..models import Briefing, GlossaryTerm, Participant, User
from ..schemas import (
    BriefingOut, BriefingUpdateIn, GeneralBriefingContent, GenerateResult, GlossaryOut, GlossaryUpdateIn,
    ParticipantBriefingOut, ParticipantOwnerOut, PersonalBriefingContent, PublicBriefingOut,
)
from ..services.ai import AIError
from ..services.briefing_service import generate_all, regenerate_personal

router = APIRouter(prefix="/api", tags=["briefings"])


def _ai_fail(e: AIError):
    return HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 생성에 실패했습니다. 잠시 후 다시 시도해 주세요. ({e})")


@router.post("/meetings/{meeting_id}/briefings/generate", response_model=GenerateResult)
def generate(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """공통 브리핑 + 전문 용어 + 참석자별 브리핑을 생성(재생성 시 기존 내용 교체)."""
    m = get_meeting_for_edit(meeting_id, db, user)
    try:
        return generate_all(db, m)
    except AIError as e:
        db.rollback()
        raise _ai_fail(e)


@router.get("/meetings/{meeting_id}/briefing", response_model=BriefingOut | None)
def get_general(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for_view(meeting_id, db, user)
    return db.scalar(select(Briefing).where(Briefing.meeting_id == m.id, Briefing.participant_id.is_(None)))


@router.put("/briefings/{bid}", response_model=BriefingOut)
def update_briefing(bid: int, body: BriefingUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = db.get(Briefing, bid)
    if b is None:
        raise HTTPException(404, "브리핑을 찾을 수 없습니다.")
    get_meeting_for_edit(b.meeting_id, db, user)
    schema = GeneralBriefingContent if b.participant_id is None else PersonalBriefingContent
    try:
        b.content = schema.model_validate(body.content).model_dump()
    except ValidationError as e:
        raise HTTPException(422, f"브리핑 형식이 올바르지 않습니다: {e.errors()[:3]}")
    b.is_edited = True
    db.commit()
    db.refresh(b)
    return b


@router.get("/meetings/{meeting_id}/participant-briefings", response_model=list[ParticipantBriefingOut])
def participant_briefings(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for_view(meeting_id, db, user)
    editable = can_edit(m, user)
    by_pid = {b.participant_id: b for b in db.scalars(select(Briefing).where(Briefing.meeting_id == m.id, Briefing.participant_id.is_not(None)))}
    out = []
    for p in m.participants:
        # 생성자/관리자는 전원, 일반 참석자는 본인 것만 열람
        if not editable and p.email != user.email.lower():
            continue
        po = ParticipantOwnerOut.model_validate(p)
        if not editable:
            po = po.model_copy(update={"access_token": None})
        out.append(ParticipantBriefingOut(participant=po, briefing=by_pid.get(p.id)))
    return out


@router.post("/participants/{pid}/briefing/regenerate", response_model=BriefingOut)
def regenerate(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(Participant, pid)
    if p is None:
        raise HTTPException(404, "참석자를 찾을 수 없습니다.")
    m = get_meeting_for_edit(p.meeting_id, db, user)
    try:
        return regenerate_personal(db, m, p)
    except AIError as e:
        db.rollback()
        raise _ai_fail(e)


# ---------- Glossary ----------
@router.get("/meetings/{meeting_id}/glossary", response_model=list[GlossaryOut])
def glossary(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_meeting_for_view(meeting_id, db, user).glossary


def _term_for_edit(tid: int, db: Session, user: User) -> GlossaryTerm:
    t = db.get(GlossaryTerm, tid)
    if t is None:
        raise HTTPException(404, "용어를 찾을 수 없습니다.")
    get_meeting_for_edit(t.meeting_id, db, user)
    return t


@router.put("/glossary/{tid}", response_model=GlossaryOut)
def update_term(tid: int, body: GlossaryUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = _term_for_edit(tid, db, user)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(t, k, v)
    t.is_edited = True
    t.is_uncertain = False if body.easy_explanation else t.is_uncertain
    db.commit()
    db.refresh(t)
    return t


@router.delete("/glossary/{tid}", status_code=204)
def delete_term(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = _term_for_edit(tid, db, user)
    db.delete(t)
    db.commit()


# ---------- Public personal briefing (이메일 링크, 로그인 불필요) ----------
@router.get("/public/briefings/{token}", response_model=PublicBriefingOut)
def public_briefing(token: str, db: Session = Depends(get_db)):
    p = db.scalar(select(Participant).where(Participant.access_token == token)) if len(token) >= 20 else None
    if p is None:
        raise HTTPException(404, "브리핑을 찾을 수 없습니다. 링크를 다시 확인해 주세요.")
    m = p.meeting
    personal = db.scalar(select(Briefing).where(Briefing.participant_id == p.id))
    general = db.scalar(select(Briefing).where(Briefing.meeting_id == m.id, Briefing.participant_id.is_(None)))
    related = {t.lower() for t in (personal.content.get("related_terms", []) if personal else [])}
    terms = [g for g in m.glossary if g.term.lower() in related] or list(m.glossary)[:8]
    return PublicBriefingOut(
        meeting_title=m.title, meeting_purpose=m.purpose, start_at=m.start_at, end_at=m.end_at, location=m.location,
        online_url=m.online_url, agenda_items=m.agenda_items, participant_name=p.name, participant_role=p.role,
        participant_responsibility=p.responsibility, personal=personal,
        checklist=(general.content.get("checklist", []) if general else []), glossary=terms,
    )
