from __future__ import annotations

import json
import logging
import os
from typing import Any


class JsonFormatter(logging.Formatter):
	def format(self, record: logging.LogRecord) -> str:
		payload: dict[str, Any] = {
			"level": record.levelname,
			"logger": record.name,
			"msg": record.getMessage(),
			"time": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
		}
		if record.exc_info:
			payload["exc_info"] = self.formatException(record.exc_info)
		return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
	"""Инициализация логирования; формат JSON включается через переменную окружения."""
	level = os.getenv("LOG_LEVEL", "INFO").upper()
	use_json = os.getenv("LOG_JSON", "false").lower() in ("1", "true", "yes")
	root = logging.getLogger()
	root.setLevel(level)
	# Очистить имеющиеся обработчики
	for h in list(root.handlers):
		root.removeHandler(h)
		try:
			h.close()
		except Exception:
			pass
	handler = logging.StreamHandler()
	if use_json:
		handler.setFormatter(JsonFormatter())
	else:
		handler.setFormatter(logging.Formatter("% (asctime)s % (levelname)s % (name)s - % (message)s".replace(" ", "").replace("%", "%")))
	root.addHandler(handler) 