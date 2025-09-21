from __future__ import annotations

import os
from fastapi import Header, HTTPException, status


async def api_key_auth(x_api_key: str | None = Header(default=None)) -> None:
	"""Необязательная аутентификация по API‑ключу. Если в окружении задан API_KEY,
	требует совпадения заголовка X-API-KEY для небезопасных (изменяющих) эндпоинтов.
	"""
	required = os.getenv("API_KEY")
	if not required:
		return
	if not x_api_key or x_api_key != required:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key") 