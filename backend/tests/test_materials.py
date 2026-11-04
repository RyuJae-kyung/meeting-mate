from .conftest import make_docx, make_pdf, make_pptx


def upload(client, auth, mid, files):
    return client.post(f"/api/meetings/{mid}/materials", files=[("files", f) for f in files], headers=auth)


def test_upload_and_extract_all_types(client, auth, meeting):
    mid = meeting["id"]
    txt = "회의 메모\n\n이번 분기 CRM 교체 검토가 필요하다.\n\n일정은 미정이다.".encode("utf-8")
    r = upload(client, auth, mid, [
        ("plan.pdf", make_pdf(), "application/pdf"),
        ("req.docx", make_docx(), "application/octet-stream"),
        ("schedule.pptx", make_pptx(), "application/octet-stream"),
        ("memo.txt", txt, "text/plain"),
    ])
    assert r.status_code == 201, r.text
    mats = {m["original_filename"]: m for m in r.json()}
    assert all(m["status"] == "processed" for m in mats.values()), mats
    assert mats["plan.pdf"]["title"] == "MES ERP 연동 계획서"
    assert "MES" in mats["plan.pdf"]["keywords"]
    assert mats["req.docx"]["title"] == "요구사항 정의서"
    assert mats["schedule.pptx"]["title"] == "프로젝트 일정"
    assert mats["memo.txt"]["summary"].startswith("[Mock 요약")
    assert mats["memo.txt"]["summary_source"] == "mock"
    d = client.get(f"/api/materials/{mats['plan.pdf']['id']}", headers=auth).json()
    assert [s["loc"] for s in d["segments"]] == ["p.1", "p.2"]
    d = client.get(f"/api/materials/{mats['req.docx']['id']}", headers=auth).json()
    assert any(s["loc"] == "표 1" and "SLA" in s["text"] for s in d["segments"])
    d = client.get(f"/api/materials/{mats['schedule.pptx']['id']}", headers=auth).json()
    assert d["segments"][0]["loc"] == "슬라이드 1"
    # 재분석 / 삭제
    assert client.post(f"/api/materials/{mats['memo.txt']['id']}/reanalyze", headers=auth).json()["status"] == "processed"
    assert client.delete(f"/api/materials/{mats['memo.txt']['id']}", headers=auth).status_code == 204
    assert len(client.get(f"/api/meetings/{mid}/materials", headers=auth).json()) == 3


def test_cp949_txt(client, auth, meeting):
    r = upload(client, auth, meeting["id"], [("old.txt", "구형 인코딩 문서입니다. ERP 교체".encode("cp949"), "text/plain")])
    assert r.json()[0]["status"] == "processed" and "ERP" in r.json()[0]["keywords"]


def test_validation(client, auth, meeting):
    mid = meeting["id"]
    assert upload(client, auth, mid, [("a.exe", b"MZ...", "application/octet-stream")]).status_code == 415
    assert upload(client, auth, mid, [("big.txt", b"a" * (1024 * 1024 + 1), "text/plain")]).status_code == 413
    assert upload(client, auth, mid, [("empty.txt", b"", "text/plain")]).status_code == 400
    # 확장자 위장 → 저장은 되지만 분석 실패로 기록
    r = upload(client, auth, mid, [("fake.pdf", b"not a pdf at all", "application/pdf")])
    assert r.status_code == 201 and r.json()[0]["status"] == "failed" and "PDF" in r.json()[0]["error"]
    r = upload(client, auth, mid, [("fake.docx", b"PK\x03\x04garbage", "application/octet-stream")])
    assert r.json()[0]["status"] == "failed"


def test_blank_pdf_reports_no_text(client, auth, meeting):
    import pymupdf

    d = pymupdf.open(); d.new_page()
    r = upload(client, auth, meeting["id"], [("scan.pdf", d.tobytes(), "application/pdf")])
    assert r.json()[0]["status"] == "failed" and "텍스트" in r.json()[0]["error"]


def test_upload_forbidden_for_invited(client, auth, meeting):
    from .conftest import register

    h = register(client, "dev@test.com", "김개발")
    assert upload(client, h, meeting["id"], [("a.txt", b"hello world text", "text/plain")]).status_code == 403
