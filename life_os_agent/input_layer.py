"""Input abstraction for text and voice-ready channels."""

from __future__ import annotations

from dataclasses import dataclass

from .models import InputSource, UserInput


@dataclass(slots=True)
class InputAdapter:
    """Normalizes incoming payloads into typed UserInput."""

    def from_text(self, text: str, confidence: float = 1.0) -> UserInput:
        """Create a text-based user input object."""
        return UserInput(text=text.strip(), source=InputSource.TEXT, confidence=confidence)

    def from_voice_transcript(
        self,
        transcript: str,
        confidence: float,
        metadata: dict[str, str] | None = None,
    ) -> UserInput:
        """Create a voice-origin input object with placeholder metadata."""
        return UserInput(
            text=transcript.strip(),
            source=InputSource.VOICE,
            confidence=confidence,
            metadata=metadata or {},
        )
