from __future__ import annotations

import abc
from typing import Iterable

from .types import AlertEvent


class Notifier(abc.ABC):
	@abc.abstractmethod
	async def send(self, event: AlertEvent) -> None:
		...


class CompositeNotifier(Notifier):
	def __init__(self, channels: Iterable[Notifier]):
		self._channels = list(channels)

	async def send(self, event: AlertEvent) -> None:
		for ch in self._channels:
			try:
				await ch.send(event)
			except Exception:
				# намеренно глушим исключения каналов, чтобы не ронять процесс
				pass 