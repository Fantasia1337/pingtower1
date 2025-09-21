from __future__ import annotations

import asyncio
from typing import Optional

import aiohttp

from .base import Notifier
from .types import AlertEvent


class TelegramNotifier(Notifier):
	def __init__(self, bot_token: str, chat_id: str, *, connect_timeout_s: float = 3.0, read_timeout_s: float = 5.0) -> None:
		self._bot_token = bot_token
		self._chat_id = chat_id
		self._connect_timeout_s = connect_timeout_s
		self._read_timeout_s = read_timeout_s

	async def send(self, event: AlertEvent) -> None:
		# формируем текст без спец символов
		text = f"{event.title}\n{event.message}\nservice_id={event.service_id} ts={event.ts.isoformat()}"
		# ограничение длины сообщения Telegram ~4096 символов
		if len(text) > 4096:
			text = text[:4096]
		url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
		payload = {"chat_id": self._chat_id, "text": text}

		timeout = aiohttp.ClientTimeout(connect=self._connect_timeout_s, total=self._connect_timeout_s + self._read_timeout_s)
		try:
			async with aiohttp.ClientSession(timeout=timeout) as session:
				async with session.post(url, json=payload) as resp:
					# игнорируем тело, проверяем только код
					_ = await resp.read()
					# не бросаем исключение при 4xx, 5xx, просто завершаем
		except Exception:
			# мягко гасим любые ошибки отправки
			return 