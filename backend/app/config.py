"""애플리케이션 설정. 모든 민감 정보는 환경변수(.env)로만 주입한다."""
import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"  # development | production | test

    DATABASE_URL: str = "postgresql+psycopg://meetingmate:meetingmate@localhost:5432/meetingmate"

    JWT_SECRET: str = ""
    JWT_EXPIRE_MINUTES: int = 60 * 24

    # 관리자 권한을 부여할 이메일(콤마 구분)
    ADMIN_EMAILS: str = ""

    # AI: auto = OPENAI_API_KEY 있으면 openai, 없으면 mock
    AI_PROVIDER: str = "auto"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TIMEOUT_SECONDS: float = 90.0
    AI_MAX_CONTEXT_CHARS: int = 60000

    # Email: auto = RESEND_API_KEY 있으면 resend, 없으면 mock
    EMAIL_PROVIDER: str = "auto"
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "Meeting Mate <onboarding@resend.dev>"

    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = "http://localhost:5173"
    DISPLAY_TIMEZONE: str = "Asia/Seoul"

    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 20

    # 후속 업무 마감 알림: 마감 N일 전부터 (미완료 + 알림 켜짐 + 미발송) 1회 발송
    TASK_REMINDER_DAYS_BEFORE: int = 1
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_INTERVAL_SECONDS: int = 30

    @property
    def database_url(self) -> str:
        url = self.DATABASE_URL
        # Render/Railway 등은 postgres:// 또는 postgresql:// 형식을 제공한다.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def admin_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()}

    @property
    def ai_mode(self) -> str:
        if self.AI_PROVIDER == "auto":
            return "openai" if self.OPENAI_API_KEY else "mock"
        return self.AI_PROVIDER

    @property
    def email_mode(self) -> str:
        if self.EMAIL_PROVIDER == "auto":
            return "resend" if self.RESEND_API_KEY else "mock"
        return self.EMAIL_PROVIDER


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.JWT_SECRET:
        if s.APP_ENV == "production":
            raise RuntimeError("JWT_SECRET 환경변수가 필요합니다.")
        # 개발 환경: 프로세스마다 임의 키 (재시작 시 기존 토큰 무효화)
        s.JWT_SECRET = secrets.token_urlsafe(48)
    return s
