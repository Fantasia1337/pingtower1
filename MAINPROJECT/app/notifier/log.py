from __future__ import annotations

import logging

from .base import Notifier
from .types import AlertEvent


_level_map = {
	"info": logging.INFO,
	"warn": logging.WARN,
	"error": logging.ERROR,
}


class LogNotifier(Notifier):
	def __init__(self) -> None:
		self._logger = logging.getLogger("notifier.log")

	async def send(self, event: AlertEvent) -> None:
		lvl = _level_map.get(event.level, logging.INFO)
		self._logger.log(
			lvl,
			"title=%s, msg=%s, service_id=%s, ts=%s",
			event.title,
			event.message,
			event.service_id,
			event.ts.isoformat(),
		) 