from __future__ import annotations

import os
import time
from typing import Dict
from fastapi import Request, HTTPException, status


class TokenBucket:
	def __init__(self, rate_per_minute: int, burst: int) -> None:
		self.capacity = max(1, int(burst))
		self.tokens = self.capacity
		self.rate = max(1.0, float(rate_per_minute)) / 60.0
		self.timestamp = time.monotonic()

	def allow(self) -> bool:
		"""Алгоритм токен-бакета: возвращает True, если запрос можно пропустить сейчас."""
		now = time.monotonic()
		elapsed = now - self.timestamp
		self.timestamp = now
		self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
		if self.tokens >= 1.0:
			self.tokens -= 1.0
			return True
		return False


_buckets: Dict[str, TokenBucket] = {}


async def rate_limit(request: Request) -> None:
	"""Простейший лимитер по IP, управляется переменными окружения RATE_LIMIT_*.
	Подключается как зависимость FastAPI к читающим эндпоинтам."""
	if os.getenv("RATE_LIMIT_ENABLE", "false").lower() not in ("1", "true", "yes"):
		return
	limit = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
	burst = int(os.getenv("RATE_LIMIT_BURST", "20"))
	ip = request.client.host if request.client else "unknown"
	bucket = _buckets.get(ip)
	if bucket is None:
		bucket = TokenBucket(limit, burst)
		_buckets[ip] = bucket
	if not bucket.allow():
		raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded") 