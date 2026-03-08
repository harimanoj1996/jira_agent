"""Audit logging and lightweight memory store."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AuditStore:
    """In-memory event store for traceability and future analytics adapters."""

    events: list[dict[str, Any]] = field(default_factory=list)

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Log structured event locally and via Python logging."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        self.events.append(entry)
        logger.debug("audit_event %s", entry)
