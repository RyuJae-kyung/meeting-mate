from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user, get_meeting_for_edit, get_meeting_for_view
from ..models import User
from ..schemas import MeetingResultOut, ResultConfirmIn, TaskOut
from ..services.ai import AIError
from ..services.extraction import ALLOWED_TYPES, ExtractionError, detect_type, extract
from ..services.result_service import analyze, confirm
from .tasks import to_task_out

router = APIRouter(prefix="/api", tags=["results"])
MAX_TEXT = 200_000


@router.get("/meetings/{meeting_id}/result", response_model=MeetingResultOut | None)
def get_result(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_meeting_for_view(meeting_id, db, user).result


@router.post("/meetings/{meeting_id}/result/analyze", response_model=MeetingResultOut)
async def analyze_result(meeting_id: int, text: str = Form(""), file: UploadFile | None = File(None),
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """회의 내용 텍스트 그리고/또는 회의록 파일(PDF/DOCX/PPTX/TXT)을 분석해 초안을 만든다. 업무는 아직 생성하지 않는다."""
    m = get_meeting_for_edit(meeting_id, db, user)
    parts, filename = [], None
    if text.strip():
        parts.append(text.strip())
    if file is not None and file.filename:
        filename = file.filename[:255]
        ftype = detect_type(filename)
        if ftype is None:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"지원하지 않는 회의록 형식입니다. ({', '.join(t.upper() for t in ALLOWED_TYPES)}만 가능)")
        max_bytes = get_settings().MAX_UPLOAD_MB * 1024 * 1024
        data = await file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"파일 용량은 {get_settings().MAX_UPLOAD_MB}MB 이하여야 합니다.")
        try:
            doc = await run_in_threadpool(extract, ftype, data)
        except ExtractionError as e:
            raise HTTPException(422, f"회의록 파일 분석 실패: {e}")
        parts.append(doc.text)
    raw = "\n\n".join(parts).strip()
    if len(raw) < 10:
        raise HTTPException(422, "분석할 회의 내용을 입력하거나 회의록 파일을 업로드해 주세요.")
    if len(raw) > MAX_TEXT:
        raise HTTPException(422, f"회의 내용이 너무 깁니다 ({MAX_TEXT:,}자 이하).")
    try:
        return await run_in_threadpool(analyze, db, m, raw, filename)
    except AIError as e:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 분석에 실패했습니다. 잠시 후 다시 시도해 주세요. ({e})")


@router.post("/meetings/{meeting_id}/result/confirm")
def confirm_result(meeting_id: int, body: ResultConfirmIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """사용자가 확인·수정한 결과를 저장하고 후속 업무를 생성한다."""
    m = get_meeting_for_edit(meeting_id, db, user)
    result, tasks = confirm(db, m, user, body)
    return {"result": MeetingResultOut.model_validate(result), "tasks": [to_task_out(t, user, db) for t in tasks], "meeting_status": m.status}
