"""회의 자료(PDF/DOCX/PPTX/TXT) 텍스트 추출 및 키워드 분석.

각 텍스트 조각(segment)에 위치(p.N / 슬라이드 N / 문단 N)를 붙여 저장해
AI 답변·브리핑에서 출처를 표시할 수 있게 한다.
"""
import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field

ALLOWED_TYPES = ("pdf", "docx", "pptx", "txt")


class ExtractionError(Exception):
    pass


@dataclass
class ExtractedDoc:
    title: str | None
    segments: list[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(s["text"] for s in self.segments)


def detect_type(filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext if ext in ALLOWED_TYPES else None


def validate_signature(file_type: str, data: bytes) -> None:
    """확장자만 바꾼 파일을 거르기 위해 파일 시그니처를 확인한다."""
    if file_type == "pdf":
        if not data[:1024].lstrip().startswith(b"%PDF"):
            raise ExtractionError("PDF 파일 형식이 올바르지 않습니다.")
    elif file_type in ("docx", "pptx"):
        if not data.startswith(b"PK"):
            raise ExtractionError(f"{file_type.upper()} 파일 형식이 올바르지 않습니다.")
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile as e:
            raise ExtractionError(f"{file_type.upper()} 파일이 손상되었습니다.") from e
        marker = "word/" if file_type == "docx" else "ppt/"
        if not any(n.startswith(marker) for n in names):
            raise ExtractionError(f"{file_type.upper()} 파일 형식이 올바르지 않습니다.")
    elif file_type == "txt":
        if b"\x00" in data[:4096]:
            raise ExtractionError("텍스트 파일이 아닌 것으로 보입니다.")


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf(data: bytes) -> ExtractedDoc:
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # pymupdf는 다양한 예외를 던진다
        raise ExtractionError(f"PDF를 열 수 없습니다: {e}") from e
    if doc.needs_pass:
        raise ExtractionError("암호가 걸린 PDF는 분석할 수 없습니다.")
    segments = []
    for i, page in enumerate(doc):
        t = _clean(page.get_text("text"))
        if t:
            segments.append({"loc": f"p.{i + 1}", "text": t})
    title = (doc.metadata or {}).get("title") or None
    doc.close()
    return ExtractedDoc(title=title, segments=segments)


def _extract_docx(data: bytes) -> ExtractedDoc:
    import docx

    try:
        d = docx.Document(io.BytesIO(data))
    except Exception as e:
        raise ExtractionError(f"DOCX를 열 수 없습니다: {e}") from e
    segments: list[dict] = []
    title = d.core_properties.title or None
    n = 0
    for p in d.paragraphs:
        t = _clean(p.text)
        if not t:
            continue
        n += 1
        if title is None and (p.style is not None and p.style.name.lower().startswith(("title", "heading"))):
            title = t
        segments.append({"loc": f"문단 {n}", "text": t})
    for ti, table in enumerate(d.tables, start=1):
        rows = []
        for row in table.rows:
            cells = [_clean(c.text) for c in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            segments.append({"loc": f"표 {ti}", "text": "\n".join(rows)})
    return ExtractedDoc(title=title, segments=segments)


def _extract_pptx(data: bytes) -> ExtractedDoc:
    from pptx import Presentation

    try:
        prs = Presentation(io.BytesIO(data))
    except Exception as e:
        raise ExtractionError(f"PPTX를 열 수 없습니다: {e}") from e
    segments = []
    title = prs.core_properties.title or None
    for i, slide in enumerate(prs.slides, start=1):
        parts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                t = _clean(shape.text_frame.text)
                if t:
                    parts.append(t)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    cells = [_clean(c.text) for c in row.cells]
                    if any(cells):
                        parts.append(" | ".join(cells))
        if slide.has_notes_slide:
            notes = _clean(slide.notes_slide.notes_text_frame.text)
            if notes:
                parts.append(f"[발표자 노트] {notes}")
        if parts:
            segments.append({"loc": f"슬라이드 {i}", "text": "\n".join(parts)})
        if title is None and slide.shapes.title is not None and slide.shapes.title.text.strip():
            title = slide.shapes.title.text.strip()
    return ExtractedDoc(title=title, segments=segments)


def _extract_txt(data: bytes) -> ExtractedDoc:
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ExtractionError("텍스트 인코딩을 인식할 수 없습니다 (UTF-8 또는 CP949 권장).")
    text = _clean(text)
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    segments = [{"loc": f"문단 {i}", "text": b} for i, b in enumerate(blocks, start=1)]
    first_line = text.split("\n", 1)[0].strip() if text else None
    title = first_line[:200] if first_line and len(first_line) <= 120 else None
    return ExtractedDoc(title=title, segments=segments)


def extract(file_type: str, data: bytes) -> ExtractedDoc:
    validate_signature(file_type, data)
    fn = {"pdf": _extract_pdf, "docx": _extract_docx, "pptx": _extract_pptx, "txt": _extract_txt}[file_type]
    doc = fn(data)
    if not doc.segments:
        hint = " (스캔 이미지로 된 PDF는 텍스트 추출이 되지 않습니다)" if file_type == "pdf" else ""
        raise ExtractionError("파일에서 텍스트를 찾을 수 없습니다." + hint)
    if doc.title:
        doc.title = doc.title.strip()[:300] or None
    if not doc.title:
        first = doc.segments[0]["text"].split("\n", 1)[0].strip()
        doc.title = first[:120] if first else None
    return doc


# ---------- 키워드 (AI 없이 로컬 계산) ----------
_KO_SUFFIX = re.compile(
    r"(으로써|으로서|에서는|에게서|이라는|라는|에서|에게|으로|부터|까지|하고|이며|이고|입니다|합니다|하는|하여|해서|"
    r"은|는|이|가|을|를|의|에|로|와|과|도|만|및)$"
)
_STOP = {
    "그리고", "그러나", "하지만", "또한", "따라서", "이번", "관련", "대한", "위한", "통해", "있는", "없는", "있다", "한다",
    "합니다", "있습니다", "됩니다", "경우", "내용", "사항", "진행", "예정", "기존", "현재", "부분", "모든", "각각", "해당",
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "will", "not", "you", "our", "have",
}


def extract_keywords(text: str, top_n: int = 10) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+\-/.]*[A-Za-z0-9+]|[가-힣]{2,}", text)
    counter: Counter[str] = Counter()
    display: dict[str, str] = {}
    for tok in tokens:
        if re.match(r"[가-힣]", tok):
            tok = _KO_SUFFIX.sub("", tok)
            if len(tok) < 2:
                continue
        key = tok.lower()
        if key in _STOP or len(key) < 2:
            continue
        counter[key] += 1
        # 대문자 약어(MES, ERP)는 원형을 우선 노출
        if key not in display or tok.isupper():
            display[key] = tok
    return [display[k] for k, _ in counter.most_common(top_n)]
