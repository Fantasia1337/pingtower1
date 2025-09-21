import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
import os
import random
import json

from app.checker import URLChecker, recheck_service
from app.notifier import AlertEvent
from app.notifier.factory import build_notifier_from_env
from app.db import repo

logger = logging.getLogger(__name__)


class Scheduler:
	def __init__(self, *, global_concurrency: int = 10, tick_seconds: int = 10, global_rps: Optional[int] = None) -> None:
		self._global_concurrency = max(1, global_concurrency)
		self._tick_seconds = max(1, tick_seconds)
		self._global_rps = max(1, global_rps) if global_rps else None
		self._stop_event = asyncio.Event()
		self._notifier = build_notifier_from_env()
		self._next_due_ts: Dict[int, datetime] = {}
		self._manual_queue: asyncio.Queue[int] = asyncio.Queue()
		self._svc_limits = self._load_service_limits()

	def _load_service_limits(self) -> Dict[str, Dict[str, int]]:
		"""Прочитать JSON из переменной окружения SERVICE_LIMITS_JSON: [{"pattern":"example\\.com","concurrency":2,"rps":1}], поддержка regex."""
		try:
			raw = os.getenv("SERVICE_LIMITS_JSON", "[]")
			items = json.loads(raw)
			cfg: Dict[str, Dict[str, int]] = {}
			for item in items:
				pat = str(item.get("pattern",""))
				if not pat:
					continue
				cfg[pat] = {
					"concurrency": int(item.get("concurrency", 0)),
					"rps": int(item.get("rps", 0)),
				}
			record = cfg
			return record
		except Exception:
			return {}

	def _match_limits(self, url: str) -> tuple[int|None, int|None]:
		import re
		for pat, vals in self._svc_limits.items():
			try:
				if re.search(pat, url):
					c = vals.get("concurrency") or None
					r = vals.get("rps") or None
					return c, r
			except Exception:
				continue
		return None, None

	async def run(self) -> None:
		logger.info("Scheduler started: tick=%ss, concurrency=%s, rps=%s", self._tick_seconds, self._global_concurrency, self._global_rps)
		while not self._stop_event.is_set():
			try:
				# сначала обрабатываем ручные запросы повышенного приоритета
				await self._drain_manual_queue()
				await self._tick()
			except Exception as e:
				logger.exception("scheduler tick failed: %s", e)
			finally:
				try:
					await asyncio.wait_for(self._stop_event.wait(), timeout=self._tick_seconds)
				except asyncio.TimeoutError:
					pass

	def stop(self) -> None:
		self._stop_event.set()

	async def enqueue_manual(self, service_id: int) -> None:
		"""Поместить сервис в ручную очередь для немедленной проверки."""
		try:
			await self._manual_queue.put(service_id)
		except Exception:
			pass

	async def _drain_manual_queue(self) -> None:
		items: list[int] = []
		try:
			while True:
				items.append(self._manual_queue.get_nowait())
		except Exception:
			pass
		# метрика размера очереди
		try:
			from app.metrics import set_manual_queue_size
			set_manual_queue_size(self._manual_queue.qsize())
		except Exception:
			pass
		if not items:
			return
		semaphore = asyncio.Semaphore(self._global_concurrency)
		async with URLChecker(max_concurrent=self._global_concurrency) as checker:
			await asyncio.gather(*[self._recheck_service(concurrency=semaphore, checker=checker, svc_id=sid) for sid in items])

	async def _tick(self) -> None:
		# TTL cleanup (best-effort) по расписанию раз в N тиков
		try:
			if random.randint(0, 9) == 0:  # ~каждые 10 тиков
				repo.ttl_cleanup_check_results(int(os.getenv("TTL_CLEANUP_HOURS", "720")))
		except Exception:
			pass
		services = repo.list_services()
		if not services:
			return

		now = datetime.now(timezone.utc)
		# инициализируем next_due для новых сервисов с небольшим джиттером
		for s in services:
			if s.id not in self._next_due_ts:
				jitter = self._compute_jitter(s.interval_s)
				self._next_due_ts[s.id] = now + timedelta(seconds=jitter)

		# определяем, какие сервисы «должны» проверяться сейчас
		dues = [s for s in services if self._next_due_ts.get(s.id, now) <= now]
		if not dues:
			return

		# назначаем время следующей проверки для выбранных сервисов
		for s in dues:
			jitter = self._compute_jitter(s.interval_s)
			self._next_due_ts[s.id] = now + timedelta(seconds=max(1, s.interval_s) + jitter)

		# ограничение по RPS: рассчитываем начальные задержки, чтобы не превысить глобальный RPS
		per_call_delay = (1.0 / self._global_rps) if self._global_rps else 0.0

		semaphore = asyncio.Semaphore(self._global_concurrency)
		async with URLChecker(max_concurrent=self._global_concurrency) as checker:
			tasks = []
			for idx, s in enumerate(dues):
				# переопределения на уровень сервиса
				per_c, per_r = self._match_limits(s.url)
				if per_c and per_c > 0:
					service_sema = asyncio.Semaphore(per_c)
				else:
					service_sema = semaphore
				initial_delay = per_call_delay * idx if per_call_delay > 0 else 0.0
				if per_r and per_r > 0:
					initial_delay = max(initial_delay, 1.0 / per_r)
				tasks.append(self._recheck_with_delay(initial_delay, concurrency=service_sema, checker=checker, svc_id=s.id))
			await asyncio.gather(*tasks)

	def _compute_jitter(self, interval_s: int) -> int:
		# джиттер до 10% от интервала, но не более 30 секунд
		max_jitter = min(max(1, int(interval_s * 0.1)), 30)
		return random.randint(0, max_jitter)

	async def _recheck_with_delay(self, delay: float, *, concurrency: asyncio.Semaphore, checker: URLChecker, svc_id: int) -> None:
		if delay > 0:
			try:
				await asyncio.wait_for(asyncio.sleep(delay), timeout=delay + 0.5)
			except asyncio.TimeoutError:
				pass
		await self._recheck_service(concurrency=concurrency, checker=checker, svc_id=svc_id)

	async def _recheck_service(self, *, concurrency: asyncio.Semaphore, checker: URLChecker, svc_id: int) -> None:
		async with concurrency:
			service = repo.get_service(svc_id)
			if service is None:
				return
			result = await recheck_service({"url": service.url, "timeout_s": service.timeout_s}, checker)
			ts = datetime.now(timezone.utc)
			repo.insert_check_result(
				service_id=service.id,
				ts=ts,
				ok=result.get("ok", False),
				status_code=(result.get("status_code") or 0),
				latency_ms=(result.get("latency_ms") or 0),
				error_text=(result.get("error_text") or ""),
			)
			# запись в ClickHouse (опционально)
			try:
				from app.clickhouse import record_check as ch_record
				ch_record(service.id, ts, ok=result.get("ok", False), status_code=result.get("status_code"), latency_ms=result.get("latency_ms"), error_text=(result.get("error_text") or ""))
			except Exception:
				pass
			await self._handle_incident_logic(service.id, result)

	async def _handle_incident_logic(self, service_id: int, result: dict) -> None:
		# 3 ошибки подряд -> открыть, 1 успешная -> закрыть
		last5 = repo.get_last_n_results(service_id, 5)
		if not last5:
			return
		open_inc = repo.get_open_incident(service_id)
		if result.get("ok"):
			# закрыть при первом успехе
			if open_inc is not None:
				repo.close_incident(open_inc.id, datetime.now(timezone.utc))
				await self._notify(service_id, level="info", title="Инцидент закрыт", message="Сервис снова доступен")
			return
		# результат — ошибка
		# если инцидент уже открыт -> возможно, эскалируем
		if open_inc is not None:
			try:
				repo.increment_open_incident_fail(open_inc.id)
			except Exception:
				pass
			# эскалация по длительности/количеству (простая): каждые 5 фейлов дублируем уведомление, но не чаще чем раз в 5 минут
			try:
				if (open_inc.fail_count + 1) % 5 == 0:
					await self._notify(service_id, level="error", title="Эскалация инцидента", message=f"Непрерывные ошибки: {open_inc.fail_count + 1}")
			except Exception:
				pass
			return
		# последовательные ошибки
		fails = 0
		for r in last5:
			if not r.ok:
				fails += 1
			else:
				break
		if fails >= 3:
			repo.open_incident(service_id, datetime.now(timezone.utc), fail_count=fails)
			await self._notify(service_id, level="error", title="Инцидент открыт", message="Сервис недоступен (3 ошибки подряд)")

	async def _notify(self, service_id: Optional[int], *, level: str, title: str, message: str) -> None:
		try:
			await self._notifier.send(AlertEvent(service_id=service_id, level=level, title=title, message=message))
		except Exception:
			# не роняем планировщик из-за канала
			pass


def from_env() -> "Scheduler":
	try:
		concurrency = int(os.getenv("GLOBAL_CONCURRENCY", "10"))
		tick = int(os.getenv("CHECK_TICK_SEC", "10"))
		global_rps = int(os.getenv("GLOBAL_RPS", "0")) or None
	except Exception:
		concurrency, tick, global_rps = 10, 10, None
	return Scheduler(global_concurrency=concurrency, tick_seconds=tick, global_rps=global_rps) 