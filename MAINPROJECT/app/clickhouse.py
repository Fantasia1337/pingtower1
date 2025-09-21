from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

_client = None
_enabled = False


def _get_client():
	global _client, _enabled
	if not _enabled:
		return None
	try:
		if _client is not None:
			return _client
		import clickhouse_connect  # type: ignore
		url = os.getenv("CLICKHOUSE_URL", "http://clickhouse:8123")
		db = os.getenv("CLICKHOUSE_DB", "pingtower")
		user = os.getenv("CLICKHOUSE_USER", "default")
		password = os.getenv("CLICKHOUSE_PASSWORD", "")
		_client = clickhouse_connect.get_client(host=url.split("://",1)[1].split(":")[0], port=int(url.split(":")[-1]), username=user, password=password, database=db)
		return _client
	except Exception:
		return None


def init_clickhouse() -> None:
	"""Инициализировать ClickHouse при включении: создать базу и таблицу."""
	global _enabled
	_enabled = os.getenv("CLICKHOUSE_ENABLE", "false").lower() in ("1", "true", "yes")
	if not _enabled:
		return
	try:
		client = _get_client()
		if client is None:
			return
		client.command("CREATE DATABASE IF NOT EXISTS pingtower")
		client.command(
			"""
			CREATE TABLE IF NOT EXISTS pingtower.check_result (
				service_id UInt32,
				ts DateTime64(3),
				ok UInt8,
				status_code Int32,
				latency_ms Int32,
				error_text String
			) ENGINE = MergeTree()
			ORDER BY (service_id, ts)
			"""
		)
	except Exception:
		return


def record_check(service_id: int, ts: datetime, *, ok: bool, status_code: Optional[int], latency_ms: Optional[int], error_text: str) -> None:
	if not _enabled:
		return
	try:
		client = _get_client()
		if client is None:
			return
		client.insert(
			"pingtower.check_result",
			[(int(service_id), ts, 1 if ok else 0, int(status_code or 0), int(latency_ms or 0), error_text or "")],
			column_names=["service_id","ts","ok","status_code","latency_ms","error_text"],
		)
	except Exception:
		return 