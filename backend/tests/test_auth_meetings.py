from .conftest import MEETING, register


def test_register_login_me(client):
    h = register(client)
    assert client.get("/api/auth/me", headers=h).json()["email"] == "owner@test.com"
    assert client.post("/api/auth/register", json={"email": "OWNER@test.com", "password": "password123", "name": "x"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "owner@test.com", "password": "wrong-pass"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "owner@test.com", "password": "password123"})
    assert r.status_code == 200 and r.json()["access_token"]
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_profile_and_password(client, auth):
    r = client.put("/api/auth/me", json={"name": "새이름", "job_title": "PM", "email_notifications": False}, headers=auth)
    assert r.json()["name"] == "새이름" and r.json()["email_notifications"] is False
    assert client.put("/api/auth/password", json={"current_password": "nope", "new_password": "newpassword1"}, headers=auth).status_code == 400
    assert client.put("/api/auth/password", json={"current_password": "password123", "new_password": "newpassword1"}, headers=auth).status_code == 204
    assert client.post("/api/auth/login", json={"email": "owner@test.com", "password": "newpassword1"}).status_code == 200


def test_admin_role_from_env(client):
    h = register(client, "admin@test.com", "관리자")
    assert client.get("/api/auth/me", headers=h).json()["role"] == "admin"


def test_meeting_crud(client, auth, meeting):
    assert meeting["status"] == "scheduled"
    assert meeting["agenda_items"] == ["1. 연동 범위 확정", "2. API 개발 일정", "3. 예산 및 리스크 검토"]
    assert len(meeting["participants"]) == 3 and meeting["participants"][0]["access_token"]
    mid = meeting["id"]
    r = client.put(f"/api/meetings/{mid}", json={"title": "수정된 제목"}, headers=auth)
    assert r.json()["title"] == "수정된 제목"
    assert client.patch(f"/api/meetings/{mid}/status", json={"status": "completed"}, headers=auth).json()["status"] == "completed"
    assert client.patch(f"/api/meetings/{mid}/status", json={"status": "bogus"}, headers=auth).status_code == 422
    lst = client.get("/api/meetings", headers=auth).json()
    assert lst[0]["participant_count"] == 3
    assert client.delete(f"/api/meetings/{mid}", headers=auth).status_code == 204
    assert client.get(f"/api/meetings/{mid}", headers=auth).status_code == 404


def test_meeting_validation(client, auth):
    bad = dict(MEETING, start_at="2030-11-10T14:00:00")  # 시간대 없음
    assert client.post("/api/meetings", json=bad, headers=auth).status_code == 422
    bad = dict(MEETING, end_at="2030-11-10T13:00:00+09:00")
    assert client.post("/api/meetings", json=bad, headers=auth).status_code == 422
    dup = dict(MEETING, participants=[MEETING["participants"][0], MEETING["participants"][0]])
    assert client.post("/api/meetings", json=dup, headers=auth).status_code == 422


def test_participants(client, auth, meeting):
    mid = meeting["id"]
    r = client.post(f"/api/meetings/{mid}/participants", json={"name": "최영업", "email": "Sales@Test.com", "role": "영업 담당자"}, headers=auth)
    assert r.status_code == 201 and r.json()["email"] == "sales@test.com"
    assert client.post(f"/api/meetings/{mid}/participants", json={"name": "중복", "email": "sales@test.com"}, headers=auth).status_code == 409
    pid = r.json()["id"]
    assert client.put(f"/api/participants/{pid}", json={"name": "최영업2", "email": "sales@test.com", "role": "영업"}, headers=auth).json()["name"] == "최영업2"
    assert client.delete(f"/api/participants/{pid}", headers=auth).status_code == 204


def test_access_control(client, auth, meeting):
    mid = meeting["id"]
    stranger = register(client, "stranger@test.com", "외부인")
    assert client.get(f"/api/meetings/{mid}", headers=stranger).status_code == 404
    assert client.put(f"/api/meetings/{mid}", json={"title": "x"}, headers=stranger).status_code == 404
    assert client.get("/api/meetings", headers=stranger).json() == []
    # 참석자로 초대된 사용자: 열람 가능, 수정 불가, 토큰 비노출
    invited = register(client, "dev@test.com", "김개발")
    r = client.get(f"/api/meetings/{mid}", headers=invited)
    assert r.status_code == 200 and r.json()["can_edit"] is False
    assert all(p["access_token"] is None for p in r.json()["participants"])
    assert client.put(f"/api/meetings/{mid}", json={"title": "x"}, headers=invited).status_code == 403
    assert client.post(f"/api/meetings/{mid}/emails/preview", json={"participant_id": 1}, headers=invited).status_code == 403
    admin = register(client, "admin@test.com", "관리자")
    assert client.put(f"/api/meetings/{mid}", json={"title": "관리자 수정"}, headers=admin).status_code == 200
