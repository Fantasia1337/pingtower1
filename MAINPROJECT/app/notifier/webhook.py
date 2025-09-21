from __future__ import annotations

import aiohttp
from .base import Notifier
from .types import AlertEvent


class WebhookNotifier(Notifier):
	"""Простой отправитель уведомлений через HTTP Webhook."""
	def __init__(self, url: str, *, connect_timeout_s: float = 3.0, read_timeout_s: float = 5.0) -> None:
		self._url = url
		self._timeout = aiohttp.ClientTimeout(connect=connect_timeout_s, total=connect_timeout_s + read_timeout_s)

	async def send(self, event: AlertEvent) -> None:
		"""Отправить событие в виде JSON на указанный URL."""
		payload = {
			"service_id": event.service_id,
			"level": event.level,
			"title": event.title,
			"message": event.message,
			"ts": event.ts.isoformat(),
		}
		try:
			async with aiohttp.ClientSession(timeout=self._timeout) as s:
				await s.post(self._url, json=payload)
		except Exception:
			return 