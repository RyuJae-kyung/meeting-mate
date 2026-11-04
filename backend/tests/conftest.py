import io
import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://meetingmate:meetingmate@localhost:5432/meetingmate_test"
)
# 테스트는 테이블을 TRUNCATE 하므로 *_test DB 에서만 실행 허용
if not os.environ["DATABASE_URL"].rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
    raise RuntimeError("테스트는 이름이 '_test'로 끝나는 데이터베이스에서만 실행할 수 있습니다: TEST_DATABASE_URL 확인")
os.environ["APP_ENV"] = "test"
os.environ["AI_PROVIDER"] = "mock"
os.environ["EMAIL_PROVIDER"] = "mock"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["UPLOAD_DIR"] = "/tmp/meetingmate-test-uploads"
os.environ["MAX_UPLOAD_MB"] = "1"
os.environ["ADMIN_EMAILS"] = "admin@test.com"
os.environ["JWT_SECRET"] = "test-secret-not-for-production-0123456789"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import Base, engine
from app.main import app
from app.services.ai import set_provider_override
from app.services.email.providers import set_email_override


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _clean():
    with engine.begin() as c:
        names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
        c.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    set_provider_override(None)
    set_email_override(None)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register(client, email="owner@test.com", name="회의주최자"):
    r = client.post("/api/auth/register", json={"email": email, "password": "password123", "name": name, "job_title": "기획"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)


MEETING = {
    "title": "스마트팩토리 MES-ERP 연동 킥오프",
    "purpose": "MES와 ERP 연동 프로젝트의 범위와 일정을 합의한다.",
    "start_at": "2030-11-10T14:00:00+09:00",
    "end_at": "2030-11-10T15:00:00+09:00",
    "location": "본사 3층 회의실",
    "online_url": "https://meet.example.com/abc",
    "agenda": "1. 연동 범위 확정\n2. API 개발 일정\n3. 예산 및 리스크 검토",
    "participants": [
        {"name": "김개발", "email": "dev@test.com", "role": "개발 담당자", "responsibility": "API 연동 및 서버 개발"},
        {"name": "이기획", "email": "plan@test.com", "role": "기획 담당자", "responsibility": "요구사항 정리"},
        {"name": "박팀장", "email": "lead@test.com", "role": "관리자", "responsibility": "예산 승인"},
    ],
}


@pytest.fixture
def meeting(client, auth):
    r = client.post("/api/meetings", json=MEETING, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def make_pdf() -> bytes:
    import pymupdf

    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((50, 72), "MES ERP 연동 계획서", fontname="korea", fontsize=14)
    p.insert_text((50, 100), "1차 범위는 생산 실적 데이터를 MES에서 ERP로 API Gateway를 통해 전송하는 것이다.", fontname="korea", fontsize=9)
    p2 = d.new_page()
    p2.insert_text((50, 72), "예산은 5천만원으로 산정되었으며 일정 지연 리스크가 있다. KPI는 데이터 정합성 99%.", fontname="korea", fontsize=9)
    return d.tobytes()


def make_docx() -> bytes:
    import docx

    d = docx.Document()
    d.add_heading("요구사항 정의서", 1)
    d.add_paragraph("고객은 실시간 재고 조회를 요구했다. SCM 담당 부서와 협의가 필요하다.")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "항목", "내용"
    t.cell(1, 0).text, t.cell(1, 1).text = "SLA", "99.9%"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def make_pptx() -> bytes:
    from pptx import Presentation

    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "프로젝트 일정"
    s.placeholders[1].text = "PoC 2주 후 MVP 개발 착수. QA 기간 1주."
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
