"""APScheduler: 예약 이메일 작업과 후속 업무 마감 알림을 주기적으로 처리한다.

- max_instances=1, coalesce=True: 같은 프로세스 안에서 작업이 겹쳐 실행되지 않음
- 여러 프로세스/인스턴스에서 동시에 돌아도 DB 원자적 선점(claim_job)으로 중복 발송되지 않음
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import get_settings
from .database import SessionLocal
from .services.email.dispatch import run_due_jobs
from .services.task_reminders import run_due_reminders

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def tick() -> None:
    db = SessionLocal()
    try:
        n = run_due_jobs(db)
        if n:
            log.info("예약 이메일 작업 %d건 처리", n)
        r = run_due_reminders(db)
        if r:
            log.info("후속 업무 마감 알림 %d건 발송", r)
    except Exception:
        log.exception("예약 이메일 처리 중 오류")
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    s = get_settings()
    if not s.SCHEDULER_ENABLED or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(tick, "interval", seconds=s.SCHEDULER_INTERVAL_SECONDS, id="email_jobs",
                       max_instances=1, coalesce=True, replace_existing=True)
    _scheduler.start()
    log.info("스케줄러 시작 (간격 %ss)", s.SCHEDULER_INTERVAL_SECONDS)


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
