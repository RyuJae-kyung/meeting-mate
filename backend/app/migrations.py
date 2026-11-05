"""가벼운 스키마 보정.

create_all 은 새 테이블만 만들고 기존 테이블에 컬럼을 추가하지 않는다.
이전 버전으로 이미 만들어진 DB를 위해 추가된 컬럼을 멱등적으로 보정한다.
(규모가 커지면 Alembic 으로 전환)
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine

STATEMENTS = [
    "ALTER TABLE email_logs ADD COLUMN IF NOT EXISTS task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS ix_email_logs_task_id ON email_logs (task_id)",
]


def run(engine: Engine) -> None:
    with engine.begin() as c:
        for stmt in STATEMENTS:
            c.execute(text(stmt))
