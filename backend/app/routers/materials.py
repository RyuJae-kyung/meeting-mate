import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user, get_meeting_for_edit, get_meeting_for_view
from ..models import MeetingMaterial, User
from ..schemas import MaterialBrief, MaterialDetail
from ..services import storage
from ..services.ai import AIError, get_ai_provider
from ..services.extraction import ALLOWED_TYPES, ExtractionError, detect_type, extract, extract_keywords

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["materials"])
MAX_FILES_PER_REQUEST = 10


def _analyze(material: MeetingMaterial, data: bytes) -> None:
    """텍스트 추출 → 키워드 → AI 요약. 실패는 material.status/error 에 기록한다."""
    try:
        doc = extract(material.file_type, data)
    except ExtractionError as e:
        material.status, material.error = "failed", str(e)
        material.extracted_text, material.segments, material.keywords = "", [], []
        return
    except Exception as e:  # 라이브러리 내부 오류
        log.exception("텍스트 추출 오류")
        material.status, material.error = "failed", f"파일 분석 중 오류가 발생했습니다: {type(e).__name__}"
        return
    material.status, material.error = "processed", None
    material.title, material.segments, material.extracted_text = doc.title, doc.segments, doc.text
    material.keywords = extract_keywords(doc.text)
    try:
        provider = get_ai_provider()
        material.summary = provider.summarize_material(material.original_filename, doc.title, doc.segments)
        material.summary_source = provider.name
    except AIError as e:
        # 텍스트 추출은 성공했으므로 자료는 사용 가능. 요약만 실패로 표시.
        material.summary, material.summary_source = None, None
        material.error = f"AI 요약 실패(텍스트 추출은 완료): {e}"


@router.post("/meetings/{meeting_id}/materials", response_model=list[MaterialBrief], status_code=201)
async def upload_materials(meeting_id: int, files: list[UploadFile] = File(...),
                           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for_edit(meeting_id, db, user)
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"한 번에 최대 {MAX_FILES_PER_REQUEST}개 파일까지 업로드할 수 있습니다.")
    max_bytes = get_settings().MAX_UPLOAD_MB * 1024 * 1024
    # 1) 모든 파일을 먼저 검증 (형식/용량) — 하나라도 잘못되면 아무것도 저장하지 않음
    payloads = []
    for f in files:
        name = (f.filename or "").strip() or "unnamed"
        ftype = detect_type(name)
        if ftype is None:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                                f"'{name}': 지원하지 않는 파일 형식입니다. ({', '.join(t.upper() for t in ALLOWED_TYPES)}만 가능)")
        data = await f.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"'{name}': 파일 용량은 {get_settings().MAX_UPLOAD_MB}MB 이하여야 합니다.")
        if not data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{name}': 빈 파일입니다.")
        payloads.append((name[:255], ftype, data))
    # 2) 저장 및 분석 (CPU 작업은 스레드풀에서)
    from starlette.concurrency import run_in_threadpool

    created = []
    for name, ftype, data in payloads:
        path = storage.save_file(m.id, ftype, data)
        mat = MeetingMaterial(meeting_id=m.id, uploaded_by=user.id, original_filename=name, stored_path=path,
                              file_type=ftype, size_bytes=len(data))
        await run_in_threadpool(_analyze, mat, data)
        db.add(mat)
        created.append(mat)
    db.commit()
    for mat in created:
        db.refresh(mat)
    return created


@router.get("/meetings/{meeting_id}/materials", response_model=list[MaterialBrief])
def list_materials(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_meeting_for_view(meeting_id, db, user).materials


def _material(mid: int, db: Session, user: User, edit: bool) -> MeetingMaterial:
    mat = db.get(MeetingMaterial, mid)
    if mat is None:
        raise HTTPException(404, "자료를 찾을 수 없습니다.")
    (get_meeting_for_edit if edit else get_meeting_for_view)(mat.meeting_id, db, user)
    return mat


@router.get("/materials/{mid}", response_model=MaterialDetail)
def get_material(mid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _material(mid, db, user, edit=False)


@router.post("/materials/{mid}/reanalyze", response_model=MaterialBrief)
def reanalyze(mid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    mat = _material(mid, db, user, edit=True)
    try:
        with open(mat.stored_path, "rb") as fh:
            data = fh.read()
    except OSError:
        raise HTTPException(status.HTTP_410_GONE, "원본 파일이 서버에 없어 재분석할 수 없습니다. 파일을 다시 업로드해 주세요.")
    _analyze(mat, data)
    db.commit()
    db.refresh(mat)
    return mat


@router.delete("/materials/{mid}", status_code=204)
def delete_material(mid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    mat = _material(mid, db, user, edit=True)
    storage.delete_file(mat.stored_path)
    db.delete(mat)
    db.commit()
