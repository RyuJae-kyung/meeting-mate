from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import EmailJob
from app.services.email.dispatch import claim_job, run_due_jobs
from app.services.email.providers import EmailSendError, SendResult, set_email_override

from .conftest import MEETING


def ready_meeting(client, auth, meeting):
    assert client.post(f"/api/meetings/{meeting['id']}/briefings/generate", headers=auth).status_code == 200
    return meeting["id"], [p["id"] for p in meeting["participants"]]


def test_preview(client, auth, meeting):
    mid, pids = ready_meeting(client, auth, meeting)
    r = client.post(f"/api/meetings/{mid}/emails/preview", json={"participant_id": pids[0]}, headers=auth)
    assert r.status_code == 200
    j = r.json()
    assert j["to"] == "dev@test.com" and j["provider"] == "mock" and j["subject"].startswith("[MOCK]")
    for must in ("스마트팩토리 MES-ERP 연동 킥오프", "2030년 11월 10일", "회의 목적", "주요 안건", "나를 위한 브리핑", "알아두면 좋은 용어", "사전 준비 체크리스트", "/b/" + meeting["participants"][0]["access_token"], "Mock AI"):
        assert must in j["html"], must


def test_preview_requires_briefing(client, auth, meeting):
    r = client.post(f"/api/meetings/{meeting['id']}/emails/preview", json={"participant_id": meeting["participants"][0]["id"]}, headers=auth)
    assert r.status_code == 409


def test_send_requires_confirm_and_briefing(client, auth, meeting):
    mid, pids = meeting["id"], [p["id"] for p in meeting["participants"]]
    assert client.post(f"/api/meetings/{mid}/emails/send", json={"participant_ids": pids, "mode": "now"}, headers=auth).status_code == 400
    assert client.post(f"/api/meetings/{mid}/emails/send", json={"participant_ids": pids, "mode": "now", "confirm": True}, headers=auth).status_code == 409
    client.post(f"/api/meetings/{mid}/briefings/generate", headers=auth)
    assert client.post(f"/api/meetings/{mid}/emails/send", json={"participant_ids": [99999], "mode": "now", "confirm": True}, headers=auth).status_code == 422


def test_send_now(client, auth, meeting):
    mid, pids = ready_meeting(client, auth, meeting)
    r = client.post(f"/api/meetings/{mid}/emails/send", json={"participant_ids": pids, "mode": "now", "confirm": True}, headers=auth)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["job"]["status"] == "done" and len(j["logs"]) == 3
    assert all(l["status"] == "sent" and l["provider"] == "mock" and l["provider_message_id"].startswith("mock-") for l in j["logs"])
    logs = client.get(f"/api/meetings/{mid}/emails/logs", headers=auth).json()
    assert len(logs) == 3
    detail = client.get(f"/api/emails/logs/{logs[0]['id']}", headers=auth).json()
    assert "<html>" in detail["body_html"]
    dash = client.get("/api/dashboard", headers=auth).json()
    assert len(dash["recent_emails"]) == 3


class FlakyProvider:
    name = "resend"

    def __init__(self):
        self.fail = True
        self.sent = []

    def send(self, to, subject, html):
        if self.fail and to == "plan@test.com":
            raise EmailSendError("422 invalid recipient (simulated)")
        self.sent.append(to)
        return SendResult(message_id=f"re_{len(self.sent)}")


def test_failure_and_retry(client, auth, meeting):
    mid, pids = ready_meeting(client, auth, meeting)
    fp = FlakyProvider()
    set_email_override(fp)
    j = client.post(f"/api/meetings/{mid}/emails/send", json={"participant_ids": pids, "mode": "now", "confirm": True}, headers=auth).json()
    assert j["job"]["status"] == "partial"
    failed = [l for l in j["logs"] if l["status"] == "failed"]
    assert len(failed) == 1 and "simulated" in failed[0]["error"]
    # 성공한 건은 재시도 불가
    ok = next(l for l in j["logs"] if l["status"] == "sent")
    assert client.post(f"/api/emails/logs/{ok['id']}/retry", headers=auth).status_code == 409
    fp.fail = False
    r = client.post(f"/api/emails/logs/{failed[0]['id']}/retry", headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "sent" and r.json()["attempts"] == 2
    assert client.post(f"/api/emails/logs/{failed[0]['id']}/retry", headers=auth).status_code == 409
    assert fp.sent.count("plan@test.com") == 1


def test_scheduled_and_before_meeting(client, auth, meeting):
    mid, pids = ready_meeting(client, auth, meeting)
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    r = client.post(f"/api/meetings/{mid}/emails/send", json={"participant_ids": pids[:1], "mode": "scheduled", "scheduled_at": future, "confirm": True}, headers=auth)
    assert r.status_code == 200 and r.json()["job"]["status"] == "pending" and r.json()["logs"] == []
    r2 = client.post(f"/api/meetings/{mid}/emails/send", json={"participant_ids": pids, "mode": "before_meeting", "minutes_before": 60, "confirm": True}, headers=auth)
    job2 = r2.json()["job"]
    assert datetime.fromisoformat(job2["scheduled_at"]) == datetime.fromisoformat(MEETING["start_at"]) - timedelta(hours=1)
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert client.post(f"/api/meetings/{mid}/emails/send", json={"participant_ids": pids, "mode": "scheduled", "scheduled_at": past, "confirm": True}, headers=auth).status_code == 422

    # 아직 예정 시각 전: 스케줄러가 처리하지 않음
    db = SessionLocal()
    assert run_due_jobs(db) == 0
    # 예정 시각 도래를 시뮬레이션
    job = db.get(EmailJob, r.json()["job"]["id"])
    job.scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert run_due_jobs(db) == 1
    assert run_due_jobs(db) == 0  # 두 번 실행해도 중복 발송 없음
    db.close()
    logs = client.get(f"/api/meetings/{mid}/emails/logs", headers=auth).json()
    assert len(logs) == 1 and logs[0]["job_id"] == job.id

    # 예약 취소
    assert client.post(f"/api/emails/jobs/{job2['id']}/cancel", headers=auth).json()["status"] == "cancelled"
    assert client.post(f"/api/emails/jobs/{job2['id']}/cancel", headers=auth).status_code == 409
    jobs = client.get(f"/api/meetings/{mid}/emails/jobs", headers=auth).json()
    assert {j["status"] for j in jobs} == {"done", "cancelled"}


def test_claim_is_atomic(client, auth, meeting):
    """두 워커가 같은 작업을 동시에 선점하려 해도 하나만 성공."""
    mid, pids = ready_meeting(client, auth, meeting)
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    jid = client.post(f"/api/meetings/{mid}/emails/send", json={"participant_ids": pids, "mode": "scheduled", "scheduled_at": future, "confirm": True}, headers=auth).json()["job"]["id"]
    import threading

    results = []
    barrier = threading.Barrier(5)

    def worker():
        s = SessionLocal()
        barrier.wait()
        results.append(claim_job(s, jid))
        s.close()

    ts = [threading.Thread(target=worker) for _ in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results.count(True) == 1
