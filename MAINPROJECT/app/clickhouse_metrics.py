from __future__ import annotations

import os
from typing import Dict
from datetime import datetime, timedelta

try:
	import clickhouse_connect  # type: ignore
except Exception:  # pragma: no cover
	clickhouse_connect = None


def has_clickhouse() -> bool:
	return os.getenv("CLICKHOUSE_ENABLE", "false").lower() in ("1", "true", "yes") and clickhouse_connect is not None


def get_latency_percentiles(hours: int = 24) -> Dict[str, int | None]:
	"""Получить перцентили задержки (p50/p95) за последние N часов из ClickHouse."""
	if not has_clickhouse():
		return {"p50": None, "p95": None}
	url = os.getenv("CLICKHOUSE_URL", "http://clickhouse:8123")
	db = os.getenv("CLICKHOUSE_DB", "pingtower")
	user = os.getenv("CLICKHOUSE_USER", "default")
	password = os.getenv("CLICKHOUSE_PASSWORD", "")
	client = clickhouse_connect.get_client(host=url.split("://",1)[1].split(":")[0], port=int(url.split(":")[-1]), username=user, password=password, database=db)
	q = f"""
		SELECT
			quantileExact(0.50)(latency_ms) AS p50,
			quantileExact(0.95)(latency_ms) AS p95
		FROM pingtower.check_result
		WHERE ts >= now() - INTERVAL {hours} HOUR AND ok = 1
	"""
	res = client.query(q)
	row = res.result_rows[0] if res.result_rows else [None, None]
	return {"p50": int(row[0]) if row[0] is not None else None, "p95": int(row[1]) if row[1] is not None else None}


def get_code_distribution(hours: int = 24) -> Dict[str, int]:
	"""Получить распределение HTTP-кодов за последние N часов из ClickHouse."""
	if not has_clickhouse():
		return {}
	url = os.getenv("CLICKHOUSE_URL", "http://clickhouse:8123")
	db = os.getenv("CLICKHOUSE_DB", "pingtower")
	user = os.getenv("CLICKHOUSE_USER", "default")
	password = os.getenv("CLICKHOUSE_PASSWORD", "")
	client = clickhouse_connect.get_client(host=url.split("://",1)[1].split(":")[0], port=int(url.split(":")[-1]), username=user, password=password, database=db)
	q = f"""
		SELECT status_code, count(*) c
		FROM pingtower.check_result
		WHERE ts >= now() - INTERVAL {hours} HOUR
		GROUP BY status_code
	"""
	res = client.query(q)
	out: Dict[str, int] = {}
	for code, cnt in res.result_rows:
		out[str(code)] = int(cnt)
	return out 