"""External model provider adapters."""

from .capriole import (
    CaprioleChatClient,
    CaprioleResponse,
    ProviderTrafficBlockedError,
)
from .elevenlabs import (
    ElevenLabsSpeechClient,
    ElevenLabsSpeechResponse,
    ElevenLabsSoundEffectResponse,
    ElevenLabsSoundEffectsClient,
)

__all__ = [
    "CaprioleChatClient",
    "CaprioleResponse",
    "ProviderTrafficBlockedError",
    "ElevenLabsSpeechClient",
    "ElevenLabsSpeechResponse",
    "ElevenLabsSoundEffectResponse",
    "ElevenLabsSoundEffectsClient",
]
