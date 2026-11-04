from ...config import get_settings
from .base import AIError, AIProvider, MaterialCtx, MeetingCtx, ParticipantCtx

_override: AIProvider | None = None


def set_provider_override(p: AIProvider | None) -> None:
    """테스트에서 공급자를 교체할 때 사용."""
    global _override
    _override = p


def get_ai_provider() -> AIProvider:
    if _override is not None:
        return _override
    mode = get_settings().ai_mode
    if mode == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider()
    from .mock_provider import MockProvider

    return MockProvider()


__all__ = ["AIError", "AIProvider", "MaterialCtx", "MeetingCtx", "ParticipantCtx", "get_ai_provider", "set_provider_override"]
