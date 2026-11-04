"""이메일 공급자. RESEND_API_KEY 가 있으면 Resend, 없으면 Mock(실제 발송 없음)."""
import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

from ...config import get_settings

log = logging.getLogger(__name__)


class EmailSendError(Exception):
    pass


@dataclass
class SendResult:
    message_id: str | None


class EmailProvider(Protocol):
    name: str

    def send(self, to: str, subject: str, html: str) -> SendResult: ...


class ResendProvider:
    name = "resend"

    def __init__(self) -> None:
        import resend

        s = get_settings()
        if not s.RESEND_API_KEY:
            raise EmailSendError("RESEND_API_KEY 가 설정되지 않았습니다.")
        resend.api_key = s.RESEND_API_KEY
        self._resend = resend
        self._from = s.EMAIL_FROM

    def send(self, to: str, subject: str, html: str) -> SendResult:
        try:
            r = self._resend.Emails.send({"from": self._from, "to": [to], "subject": subject, "html": html})
        except Exception as e:  # resend.exceptions.ResendError, 네트워크 오류
            raise EmailSendError(f"{type(e).__name__}: {e}") from e
        msg_id = r.get("id") if isinstance(r, dict) else getattr(r, "id", None)
        if not msg_id:
            raise EmailSendError(f"Resend 응답에 메시지 ID가 없습니다: {r!r}")
        return SendResult(message_id=msg_id)


class MockEmailProvider:
    """실제로 발송하지 않는다. 로그에 provider='mock' 으로 기록되고 본문은 화면에서 확인할 수 있다."""

    name = "mock"

    def send(self, to: str, subject: str, html: str) -> SendResult:
        log.info("[MOCK EMAIL] to=%s subject=%s (실제 발송되지 않음)", to, subject)
        return SendResult(message_id=f"mock-{uuid.uuid4().hex[:12]}")


_override: EmailProvider | None = None


def set_email_override(p: EmailProvider | None) -> None:
    global _override
    _override = p


def get_email_provider() -> EmailProvider:
    if _override is not None:
        return _override
    return ResendProvider() if get_settings().email_mode == "resend" else MockEmailProvider()
