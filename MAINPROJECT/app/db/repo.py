# TODO: добавить передачу session как аргумента функций (возможно Optional -_-)
# from typing import Optional
from datetime import datetime, timedelta, timezone
from typing import Iterable
from sqlalchemy import func
from .models import SessionLocal, Service, CheckResult, Incident, ERR_MAX_LEN


def _ensure_utc(ts: datetime) -> datetime:
    """Гарантировать, что datetime имеет таймзону UTC."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    elif ts.tzinfo != timezone.utc:
        return ts.astimezone(timezone.utc)
    else:
        return ts


def create_service(name: str, url: str, interval_s: int, timeout_s: int) -> Service:
    """Создать новую запись сервиса в базе данных."""
    with SessionLocal() as session:
        service = Service(
            name=name,
            url=url,
            interval_s=interval_s,
            timeout_s=timeout_s,
        )
        session.add(service)
        session.commit()
        return service


def delete_service(service_id: int) -> None:
    """Удалить сервис по ID вместе со связанными записями (через каскад)."""
    with SessionLocal() as session:
        service = session.query(Service).filter(Service.id == service_id).first()
        if service is None:
            return
        session.delete(service)
        session.commit()


def list_services() -> list[Service]:
    """Получить все сервисы из базы данных."""
    with SessionLocal() as session:
        return session.query(Service).all()


# New: получить один сервис по id

def get_service(service_id: int) -> Service | None:
    with SessionLocal() as session:
        return session.query(Service).filter(Service.id == service_id).first()


# New: обновить сервис

def update_service(service_id: int, name: str, url: str, interval_s: int, timeout_s: int) -> Service | None:
    with SessionLocal() as session:
        service = session.query(Service).filter(Service.id == service_id).first()
        if service is None:
            return None
        service.name = name
        service.url = url
        service.interval_s = interval_s
        service.timeout_s = timeout_s
        session.commit()
        session.refresh(service)
        return service


def insert_check_result(
    service_id: int,
    ts: datetime,
    ok: bool,
    status_code: int,
    latency_ms: int,
    error_text: str,
) -> None:
    """Добавить результат проверки сервиса."""
    with SessionLocal() as session:
        check_result = CheckResult(
            service_id=service_id,
            ts=_ensure_utc(ts),
            ok=ok,
            status_code=status_code,
            latency_ms=latency_ms,
            error_text=error_text[:ERR_MAX_LEN]
            if len(error_text) > ERR_MAX_LEN
            else error_text,
        )
        session.add(check_result)
        session.commit()


def get_last_status(service_id: int) -> dict | None:
    """Получить последний результат проверки для сервиса."""
    with SessionLocal() as session:
        result = (
            session.query(CheckResult)
            .filter(CheckResult.service_id == service_id)
            .order_by(CheckResult.ts.desc())
            .first()
        )
        if result is None:
            return None
        return {
            "service_id": result.service_id,
            "ts": result.ts,
            "ok": result.ok,
            "status_code": result.status_code,
            "latency_ms": result.latency_ms,
            "error_text": result.error_text,
        }


def get_history(service_id: int, limit: int) -> list[dict]:
    """Получить последние результаты проверок для сервиса (до указанного лимита)."""
    with SessionLocal() as session:
        results = (
            session.query(CheckResult)
            .filter(CheckResult.service_id == service_id)
            .order_by(CheckResult.ts.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "service_id": r.service_id,
                "ts": r.ts,
                "ok": r.ok,
                "status_code": r.status_code,
                "latency_ms": r.latency_ms,
                "error_text": r.error_text,
            }
            for r in results
        ]


def get_last_n_results(service_id: int, n: int) -> list[CheckResult]:
    """Вернуть последние N строк CheckResult (сначала самые новые)."""
    with SessionLocal() as session:
        return (
            session.query(CheckResult)
            .filter(CheckResult.service_id == service_id)
            .order_by(CheckResult.ts.desc())
            .limit(n)
            .all()
        )


# TODO: uptime_24h() -> float 0..100 вместо 0..1

def uptime_24h(service_id: int) -> float:
    """
    Рассчитать аптайм за последние 24 часа.
    Возвращает число от 0 до 1 — доля успешных проверок.
    """
    with SessionLocal() as session:
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=24)

        total_query = session.query(CheckResult).filter(
            CheckResult.service_id == service_id, CheckResult.ts >= start_time
        )
        total = total_query.count()

        if total == 0:
            return 0.0

        success = total_query.filter(CheckResult.ok).count()

        return success / total


def uptime_(service_id: int, time_span: timedelta = timedelta(hours=24), up_to: datetime | None = None) -> float:
    """Аптайм (проценты 0..100) за произвольное окно времени [up_to - time_span, up_to]."""
    with SessionLocal() as session:
        end_time = _ensure_utc(up_to or datetime.now(timezone.utc))
        start_time = end_time - time_span
        total_query = session.query(CheckResult).filter(
            CheckResult.service_id == service_id,
            CheckResult.ts >= start_time,
            CheckResult.ts <= end_time,
        )
        total = total_query.count()
        if total == 0:
            return 0.0
        success = total_query.filter(CheckResult.ok).count()
        return 100.0 * success / total


# TODO: avg_latency_24h() -> int вместо float

def avg_latency_24h(service_id: int) -> float | None:
    """
    Рассчитать среднюю задержку успешных проверок за последние 24 часа.
    Вернёт None, если успешных проверок нет.
    """
    with SessionLocal() as session:
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=24)

        result = (
            session.query(func.avg(CheckResult.latency_ms))
            .filter(
                CheckResult.service_id == service_id,
                CheckResult.ts >= start_time,
                CheckResult.ok,
            )
            .scalar()
        )

        return float(result) if result is not None else None


def avg_latency_24h_int(service_id: int) -> int | None:
    """Средняя задержка, округлённая до целых миллисекунд."""
    value = avg_latency_24h(service_id)
    return int(round(value)) if value is not None else None


def avg_latency_(service_id: int, time_span: timedelta = timedelta(hours=24), up_to: datetime | None = None) -> int | None:
    """Средняя задержка (мс, int) успешных проверок за произвольное окно."""
    with SessionLocal() as session:
        end_time = _ensure_utc(up_to or datetime.now(timezone.utc))
        start_time = end_time - time_span
        result = (
            session.query(func.avg(CheckResult.latency_ms))
            .filter(
                CheckResult.service_id == service_id,
                CheckResult.ts >= start_time,
                CheckResult.ts <= end_time,
                CheckResult.ok,
            )
            .scalar()
        )
        return int(result) if result is not None else None


def get_open_incident(service_id: int) -> Incident | None:
    """Вернуть текущий открытый инцидент для сервиса (если есть)."""
    with SessionLocal() as session:
        return (
            session.query(Incident)
            .filter(
                Incident.service_id == service_id,
                Incident.is_open,
                Incident.closed_at.is_(None),
            )
            .first()
        )


def open_incident(service_id: int, opened_at: datetime, fail_count: int) -> Incident:
    """Открыть новый инцидент."""
    with SessionLocal() as session:
        incident = Incident(
            service_id=service_id,
            opened_at=_ensure_utc(opened_at),
            fail_count=fail_count,
            is_open=True,
        )
        session.add(incident)
        session.commit()
        return incident


def close_incident(incident_id: int, closed_at: datetime) -> None:
    """Закрыть инцидент: установить closed_at и is_open=False."""
    with SessionLocal() as session:
        incident = session.query(Incident).filter(Incident.id == incident_id).first()
        if incident is None:
            return
        incident.closed_at = _ensure_utc(closed_at)
        incident.is_open = False
        session.commit()


# New: список инцидентов для UI с именем сервиса

def list_incidents(open_only: bool = True) -> list[dict]:
    with SessionLocal() as session:
        q = (
            session.query(Incident, Service.name)
            .join(Service, Service.id == Incident.service_id)
            .order_by(Incident.opened_at.desc())
        )
        if open_only:
            q = q.filter(Incident.is_open, Incident.closed_at.is_(None))
        rows = q.all()
        return [
            {
                "service_id": inc.service_id,
                "service_name": name,
                "start": inc.opened_at,
                "end": inc.closed_at,
                "is_open": inc.is_open,
            }
            for inc, name in rows
        ]


# New: инциденты конкретного сервиса (сначала последние)

def get_incidents_for_service(service_id: int, limit: int = 10) -> list[dict]:
    with SessionLocal() as session:
        rows = (
            session.query(Incident)
            .filter(Incident.service_id == service_id)
            .order_by(Incident.opened_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "start": r.opened_at,
                "end": r.closed_at,
            }
            for r in rows
        ]


def get_recent_results(service_id: int, since: datetime) -> list[CheckResult]:
	with SessionLocal() as session:
		return (
			session.query(CheckResult)
			.filter(CheckResult.service_id == service_id, CheckResult.ts >= since)
			.order_by(CheckResult.ts.asc())
			.all()
		)


def percentiles_latency(service_id: int, *, hours: int = 24, percentiles: Iterable[int] = (50, 95)) -> dict[int, int | None]:
	"""Посчитать простые перцентили задержки по успешным проверкам за последние N часов (in-memory)."""
	end = datetime.now(timezone.utc)
	start = end - timedelta(hours=hours)
	rows = [r.latency_ms for r in get_recent_results(service_id, start) if r.ok and r.latency_ms is not None]
	if not rows:
		return {p: None for p in percentiles}
	rows.sort()
	res: dict[int, int | None] = {}
	for p in percentiles:
		if not rows:
			res[p] = None
			continue
		k = (len(rows) - 1) * (p / 100.0)
		i = int(k)
		f = k - i
		if i + 1 < len(rows):
			val = rows[i] + (rows[i + 1] - rows[i]) * f
		else:
			val = rows[i]
		res[p] = int(val)
	return res


def ttl_cleanup_check_results(older_than_hours: int = 720) -> int:
	"""Удалить строки check_result старше указанного количества часов. Возвращает количество удалённых."""
	cut = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
	with SessionLocal() as session:
		q = session.query(CheckResult).filter(CheckResult.ts < cut)
		count = q.count()
		q.delete(synchronize_session=False)
		session.commit()
		return count


def increment_open_incident_fail(incident_id: int) -> None:
	with SessionLocal() as session:
		incident = session.query(Incident).filter(Incident.id == incident_id).first()
		if incident is None:
			return
		incident.fail_count = int(incident.fail_count or 0) + 1
		session.commit()
