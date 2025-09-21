from __future__ import annotations

from typing import Optional

from prometheus_client import Counter, Histogram, Gauge, CONTENT_TYPE_LATEST, generate_latest

# Глобальный реестр метрик (используется по умолчанию)

checks_total = Counter(
	"pingtower_checks_total",
	"Общее количество проверок URL",
	labelnames=("service_id", "outcome", "status_code"),
)

latency_ms = Histogram(
	"pingtower_latency_ms",
	"Задержка проверки URL в миллисекундах",
	buckets=(50, 100, 200, 300, 500, 750, 1000, 1500, 2000, 3000, 5000, 10000),
	labelnames=("service_id",),
)

manual_queue_size = Gauge(
	"pingtower_manual_queue_size",
	"Размер очереди ручных проверок",
)


def record_check(service_id: int, *, ok: bool, status_code: Optional[int], latency_value_ms: Optional[int]) -> None:
	"""Записать метрики Prometheus для одной проверки."""
	status_label = str(status_code) if status_code is not None else "none"
	checks_total.labels(service_id=str(service_id), outcome=("success" if ok else "failure"), status_code=status_label).inc()
	if latency_value_ms is not None:
		try:
			latency_ms.labels(service_id=str(service_id)).observe(max(0.0, float(latency_value_ms)))
		except Exception:
			pass


def set_manual_queue_size(n: int) -> None:
	try:
		manual_queue_size.set(max(0, int(n)))
	except Exception:
		pass


def render_metrics() -> tuple[bytes, str]:
	"""Вернуть полезную нагрузку метрик и тип контента для FastAPI-роута."""
	return generate_latest(), CONTENT_TYPE_LATEST 