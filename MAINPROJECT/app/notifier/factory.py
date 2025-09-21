from __future__ import annotations

import os
from typing import List

from .base import CompositeNotifier, Notifier
from .log import LogNotifier
from .telegram import TelegramNotifier
from .webhook import WebhookNotifier


def build_notifier_from_env() -> Notifier:
	"""Построить агрегатор нотификаторов на основе переменных окружения (лог, Telegram, Webhook)."""
	channels: List[Notifier] = [LogNotifier()]
	bot = os.getenv("TELEGRAM_BOT_TOKEN")
	chat = os.getenv("TELEGRAM_CHAT_ID")
	if bot and chat:
		channels.append(TelegramNotifier(bot, chat))
	wh = os.getenv("WEBHOOK_URL")
	if wh:
		channels.append(WebhookNotifier(wh))
	return CompositeNotifier(channels) 