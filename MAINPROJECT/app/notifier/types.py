from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AlertEvent:
	service_id: Optional[int]
	level: str  # info, warn, error
	title: str
	message: str
	ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc)) 