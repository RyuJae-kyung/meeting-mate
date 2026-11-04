"""업로드 파일 저장소 (로컬 디스크). 추출 텍스트는 DB에 저장되므로 파일이 사라져도 분석 결과는 유지된다."""
import os
import uuid
from pathlib import Path

from ..config import get_settings


def save_file(meeting_id: int, ext: str, data: bytes) -> str:
    base = Path(get_settings().UPLOAD_DIR) / str(meeting_id)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{uuid.uuid4().hex}.{ext}"  # 원본 파일명은 경로에 사용하지 않음 (경로 조작 방지)
    path.write_bytes(data)
    return str(path)


def delete_file(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
