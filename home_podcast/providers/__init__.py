"""External model provider adapters."""

from .capriole import (
    CaprioleChatClient,
    CaprioleResponse,
    ProviderTrafficBlockedError,
)
from .elevenlabs import (
    ElevenLabsDialogueClient,
    ElevenLabsDialogueResponse,
    ElevenLabsDialogueTimestampResponse,
    ElevenLabsSpeechClient,
    ElevenLabsSpeechResponse,
    ElevenLabsSoundEffectResponse,
    ElevenLabsSoundEffectsClient,
)

__all__ = [
    "CaprioleChatClient",
    "CaprioleResponse",
    "ProviderTrafficBlockedError",
    "ElevenLabsDialogueClient",
    "ElevenLabsDialogueResponse",
    "ElevenLabsDialogueTimestampResponse",
    "ElevenLabsSpeechClient",
    "ElevenLabsSpeechResponse",
    "ElevenLabsSoundEffectResponse",
    "ElevenLabsSoundEffectsClient",
]
