import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import can_edit, get_current_user, get_meeting_for_edit, get_meeting_for_view
from ..models import Briefing, Meeting, MeetingMaterial, MeetingStatus, Participant, User
from ..schemas import (
    MaterialBrief, MeetingCreateIn, MeetingDetail, MeetingListItem, MeetingStatusIn, MeetingUpdateIn,
    ParticipantIn, ParticipantOwnerOut,
)

router = APIRouter(prefix="/api", tags=["meetings"])


def visible_meetings_query(user: User):
    q = select(Meeting)
    if user.role != "admin":
        invited = exists().where(Participant.meeting_id == Meeting.id, Participant.email == user.email.lower())
        q = q.where(or_(Meeting.owner_id == user.id, invited))
    return q


def to_list_items(db: Session, meetings: list[Meeting]) -> list[MeetingListItem]:
    if not meetings:
        return []
    ids = [m.id for m in meetings]
    pc = dict(db.execute(select(Participant.meeting_id, func.count()).where(Participant.meeting_id.in_(ids)).group_by(Participant.meeting_id)).all())
    mc = dict(db.execute(select(MeetingMaterial.meeting_id, func.count()).where(MeetingMaterial.meeting_id.in_(ids)).group_by(MeetingMaterial.meeting_id)).all())
    bset = set(db.scalars(select(Briefing.meeting_id).where(Briefing.meeting_id.in_(ids), Briefing.participant_id.is_(None))).all())
    return [
        MeetingListItem.model_validate(m).model_copy(update={"participant_count": pc.get(m.id, 0), "material_count": mc.get(m.id, 0), "has_briefing": m.id in bset})
        for m in meetings
    ]


def to_detail(db: Session, m: Meeting, user: User) -> MeetingDetail:
    item = to_list_items(db, [m])[0]
    editable = can_edit(m, user)
    return MeetingDetail(
        **item.model_dump(), agenda=m.agenda, agenda_items=m.agenda_items, created_at=m.created_at, updated_at=m.updated_at,
        can_edit=editable, owner_name=m.owner.name,
        participants=[
            ParticipantOwnerOut.model_validate(p) if editable else ParticipantOwnerOut.model_validate(p).model_copy(update={"access_token": None})
            for p in m.participants
        ],
        materials=[MaterialBrief.model_validate(x) for x in m.materials],
    )


def _check_times(start, end):
    if end is not None and start is not None and end <= start:
        raise HTTPException(422, "종료 시간은 시작 시간 이후여야 합니다.")


@router.get("/meetings", response_model=list[MeetingListItem])
def list_meetings(status_: str | None = Query(None, alias="status"), q: str | None = None,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = visible_meetings_query(user)
    if status_:
        query = query.where(Meeting.status == status_)
    if q:
        query = query.where(Meeting.title.ilike(f"%{q}%"))
    meetings = db.scalars(query.order_by(Meeting.start_at.desc())).all()
    return to_list_items(db, list(meetings))


@router.post("/meetings", response_model=MeetingDetail, status_code=201)
def create_meeting(body: MeetingCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_times(body.start_at, body.end_at)
    emails = [p.email for p in body.participants]
    if len(emails) != len(set(emails)):
        raise HTTPException(422, "같은 이메일의 참석자가 중복되어 있습니다.")
    m = Meeting(owner_id=user.id, **body.model_dump(exclude={"participants"}))
    m.participants = [Participant(**p.model_dump(), access_token=secrets.token_urlsafe(32)) for p in body.participants]
    db.add(m)
    db.commit()
    db.refresh(m)
    return to_detail(db, m, user)


@router.get("/meetings/{meeting_id}", response_model=MeetingDetail)
def get_meeting(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return to_detail(db, get_meeting_for_view(meeting_id, db, user), user)


@router.put("/meetings/{meeting_id}", response_model=MeetingDetail)
def update_meeting(meeting_id: int, body: MeetingUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for_edit(meeting_id, db, user)
    data = body.model_dump(exclude_unset=True)
    for k in ("start_at", "end_at"):
        if data.get(k) is not None and data[k].tzinfo is None:
            raise HTTPException(422, "시간대 정보가 포함된 ISO 8601 형식이어야 합니다.")
    if "title" in data and data["title"] is None:
        data.pop("title")
    if "start_at" in data and data["start_at"] is None:
        data.pop("start_at")
    _check_times(data.get("start_at", m.start_at), data.get("end_at", m.end_at))
    for k, v in data.items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return to_detail(db, m, user)


@router.patch("/meetings/{meeting_id}/status", response_model=MeetingDetail)
def set_status(meeting_id: int, body: MeetingStatusIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for_edit(meeting_id, db, user)
    m.status = body.status
    db.commit()
    db.refresh(m)
    return to_detail(db, m, user)


@router.delete("/meetings/{meeting_id}", status_code=204)
def delete_meeting(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for_edit(meeting_id, db, user)
    from ..services.storage import delete_file

    for mat in m.materials:
        delete_file(mat.stored_path)
    db.delete(m)
    db.commit()


# ---------- Participants ----------
@router.post("/meetings/{meeting_id}/participants", response_model=ParticipantOwnerOut, status_code=201)
def add_participant(meeting_id: int, body: ParticipantIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for_edit(meeting_id, db, user)
    p = Participant(meeting_id=m.id, **body.model_dump(), access_token=secrets.token_urlsafe(32))
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 등록된 참석자 이메일입니다.")
    db.refresh(p)
    return p


def _participant_for_edit(pid: int, db: Session, user: User) -> Participant:
    p = db.get(Participant, pid)
    if p is None:
        raise HTTPException(404, "참석자를 찾을 수 없습니다.")
    get_meeting_for_edit(p.meeting_id, db, user)
    return p


@router.put("/participants/{pid}", response_model=ParticipantOwnerOut)
def update_participant(pid: int, body: ParticipantIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _participant_for_edit(pid, db, user)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 등록된 참석자 이메일입니다.")
    db.refresh(p)
    return p


@router.delete("/participants/{pid}", status_code=204)
def delete_participant(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _participant_for_edit(pid, db, user)
    db.delete(p)
    db.commit()


@router.get("/meetings/{meeting_id}/ics")
def meeting_ics(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from fastapi.responses import Response

    from ..config import get_settings
    from ..services.calendar import meeting_to_ics

    m = get_meeting_for_view(meeting_id, db, user)
    return Response(meeting_to_ics(m, get_settings().FRONTEND_URL), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="meeting-{m.id}.ics"'})
