"""External model provider adapters."""

from .capriole import (
    CaprioleChatClient,
    CaprioleResponse,
    ProviderTrafficBlockedError,
)
from .elevenlabs import (
    ElevenLabsSoundEffectResponse,
    ElevenLabsSoundEffectsClient,
)

__all__ = [
    "CaprioleChatClient",
    "CaprioleResponse",
    "ProviderTrafficBlockedError",
    "ElevenLabsSoundEffectResponse",
    "ElevenLabsSoundEffectsClient",
]
