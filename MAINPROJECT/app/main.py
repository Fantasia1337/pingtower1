from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Path, Query, Request, status, Depends
from app.rate_limit import rate_limit
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.notifier.factory import build_notifier_from_env
from app.db import repo
from app.checker import URLChecker, recheck_service
from app.scheduler import Scheduler, from_env
from app.metrics import render_metrics, record_check
from app.clickhouse import init_clickhouse as ch_init, record_check as ch_record
from app.clickhouse_metrics import get_latency_percentiles as ch_pctl, get_code_distribution as ch_codes, has_clickhouse as ch_has
from app.security import api_key_auth
import asyncio
import os
from pathlib import Path
from app.logging_config import setup_logging

# инициализация БД
from app.db.init_db import main as init_db_main


class ErrorResponse(BaseModel):
	code: str
	message: str


class ServiceCreate(BaseModel):
	name: str = Field(min_length=1, max_length=200)
	url: str
	interval_s: int = Field(ge=1)
	timeout_s: int = Field(ge=1)

	@field_validator("url")
	@classmethod
	def validate_url(cls, v: str) -> str:
		parsed = urlparse(v)
		if parsed.scheme not in ("http", "https"):
			raise ValueError("url must start with http or https")
		# allow/deny lists из env (регекспы через запятую)
		import os, re
		allow = os.getenv("URL_ALLOW_REGEX")
		deny = os.getenv("URL_DENY_REGEX")
		if deny:
			for pat in deny.split(","):
				pat = pat.strip()
				if pat and re.search(pat, v):
					raise ValueError("url denied by policy")
		if allow:
			ok = False
			for pat in allow.split(","):
				pat = pat.strip()
				if pat and re.search(pat, v):
					ok = True
					break
			if not ok:
				raise ValueError("url not allowed by policy")
		return v

	@field_validator("interval_s")
	@classmethod
	def validate_interval(cls, v: int) -> int:
		if v < 60:
			raise ValueError("interval_s must be >= 60")
		return v

	@field_validator("timeout_s")
	@classmethod
	def validate_timeout(cls, v: int) -> int:
		if v < 1:
			raise ValueError("timeout_s must be >= 1")
		return v


class ServiceOut(BaseModel):
	id: int
	name: str
	url: HttpUrl
	interval_s: int
	timeout_s: int


class IncidentForStatus(BaseModel):
	start: datetime
	end: Optional[datetime] = None


class StatusOut(BaseModel):
	service_id: int
	ts: datetime
	ok: bool
	status_code: Optional[int]
	latency_ms: Optional[int]
	uptime: Optional[int] = None
	incidents: Optional[List[IncidentForStatus]] = None


class HistoryItem(BaseModel):
	ts: datetime
	ok: bool
	status_code: Optional[int]
	latency_ms: Optional[int]
	error: Optional[str] = None


class RecheckResponse(BaseModel):
	queued: bool


class IncidentOut(BaseModel):
	service_id: int
	opened_at: datetime
	is_open: bool


# Модель для списка инцидентов, ожидаемая UI: { service_name, start, end }
class IncidentListItem(BaseModel):
	service_name: Optional[str] = None
	start: datetime
	end: Optional[datetime] = None


app = FastAPI(title="PingTower API", description="MVP мониторинга доступности сайтов", version="0.1.0")

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"]
)

# абсолютный путь к статике
_STATIC_DIR = (Path(__file__).resolve().parent / "static").as_posix()
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# инициализация уведомлений
notifier = build_notifier_from_env()

_scheduler: Optional[Scheduler] = None
_scheduler_task: Optional[asyncio.Task] = None


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
	return JSONResponse(status_code=exc.status_code, content=ErrorResponse(code=str(exc.status_code), message=str(exc.detail)).dict())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
	return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=ErrorResponse(code="400", message="validation error").dict())


@app.on_event("startup")
async def on_startup():
	# логирование
	try:
		setup_logging()
	except Exception:
		pass
	# убедиться, что схема БД существует
	try:
		init_db_main()
	except Exception:
		# создание best-effort
		pass
	# инициализация ClickHouse при включении
	try:
		ch_init()
	except Exception:
		pass
	global _scheduler, _scheduler_task
	try:
		concurrency = int(os.getenv("GLOBAL_CONCURRENCY", "10"))
		tick = int(os.getenv("CHECK_TICK_SEC", "10"))
	except Exception:
		concurrency, tick = 10, 10
	_scheduler = from_env()
	_scheduler_task = asyncio.create_task(_scheduler.run())


@app.on_event("shutdown")
async def on_shutdown():
	global _scheduler, _scheduler_task
	if _scheduler is not None:
		_scheduler.stop()
	if _scheduler_task is not None:
		try:
			await asyncio.wait_for(_scheduler_task, timeout=5)
		except Exception:
			pass


@app.get("/", include_in_schema=False)
async def root_index():
	return FileResponse(str(Path(_STATIC_DIR) / "index.html"))


@app.get("/health")
def health():
	return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics_endpoint():
	payload, content_type = render_metrics()
	return PlainTextResponse(payload.decode("utf-8"), media_type=content_type)


@app.get("/ready", include_in_schema=False)
def ready():
	# проверка БД и состояния планировщика
	try:
		_ = repo.list_services()
	except Exception:
		raise HTTPException(status_code=503, detail="db not ready")
	if _scheduler_task is None:
		raise HTTPException(status_code=503, detail="scheduler not running")
	return {"status": "ready"}


@app.post("/services", response_model=ServiceOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(api_key_auth)])
async def create_service(payload: ServiceCreate):
	# проверка уникальности имени
	existing = [s for s in repo.list_services() if s.name.lower() == payload.name.lower()]
	if existing:
		raise HTTPException(status_code=409, detail="service name already exists")
	service = repo.create_service(payload.name, payload.url, payload.interval_s, payload.timeout_s)
	return ServiceOut(id=service.id, name=service.name, url=service.url, interval_s=service.interval_s, timeout_s=service.timeout_s)


@app.get("/services", response_model=List[ServiceOut], dependencies=[Depends(rate_limit)])
async def list_services():
	services = repo.list_services()
	return [ServiceOut(id=s.id, name=s.name, url=s.url, interval_s=s.interval_s, timeout_s=s.timeout_s) for s in services]


@app.put("/services/{service_id}", response_model=ServiceOut, dependencies=[Depends(api_key_auth)])
async def update_service(service_id: int = Path(ge=1), payload: ServiceCreate = None):
	# проверка уникальности имени (исключая текущий)
	for other in repo.list_services():
		if other.id != service_id and other.name.lower() == payload.name.lower():
			raise HTTPException(status_code=409, detail="service name already exists")
	updated = repo.update_service(service_id, payload.name, payload.url, payload.interval_s, payload.timeout_s)
	if updated is None:
		raise HTTPException(status_code=404, detail="service not found")
	return ServiceOut(id=updated.id, name=updated.name, url=updated.url, interval_s=updated.interval_s, timeout_s=updated.timeout_s)


@app.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(api_key_auth)])
async def delete_service(service_id: int = Path(ge=1)):
	repo.delete_service(service_id)
	# Возвращаем пустой 204 без JSON-тела
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/status/{service_id}", response_model=StatusOut, dependencies=[Depends(rate_limit)])
async def get_status(service_id: int = Path(ge=1)):
	service = repo.get_service(service_id)
	if service is None:
		raise HTTPException(status_code=404, detail="service not found")
	last = repo.get_last_status(service_id)
	if last is None:
		uptime = int(repo.uptime_(service_id)) if hasattr(repo, "uptime_") else None
		incs = [IncidentForStatus(start=i["start"], end=i["end"]) for i in repo.get_incidents_for_service(service_id, limit=5)]
		return StatusOut(service_id=service_id, ts=datetime.now(timezone.utc), ok=True, status_code=200, latency_ms=0, uptime=uptime, incidents=incs)
	uptime = int(repo.uptime_(service_id)) if hasattr(repo, "uptime_") else None
	incs = [IncidentForStatus(start=i["start"], end=i["end"]) for i in repo.get_incidents_for_service(service_id, limit=5)]
	return StatusOut(service_id=service_id, ts=last["ts"], ok=last["ok"], status_code=last["status_code"], latency_ms=last["latency_ms"], uptime=uptime, incidents=incs)


@app.get("/percentiles/{service_id}")
async def get_percentiles(service_id: int = Path(ge=1)):
	service = repo.get_service(service_id)
	if service is None:
		raise HTTPException(status_code=404, detail="service not found")
	vals = repo.percentiles_latency(service_id, hours=24, percentiles=(50,95))
	return {"p50": vals.get(50), "p95": vals.get(95)}


@app.get("/services/{service_id}/history", response_model=List[HistoryItem], dependencies=[Depends(rate_limit)])
async def get_history(service_id: int = Path(ge=1), limit: int = Query(100, ge=1, le=1000)):
	service = repo.get_service(service_id)
	if service is None:
		raise HTTPException(status_code=404, detail="service not found")
	h = repo.get_history(service_id, limit)
	return [HistoryItem(ts=i["ts"], ok=i["ok"], status_code=i["status_code"], latency_ms=i["latency_ms"], error=i["error_text"]) for i in h]


async def _recheck_and_record(service_id: int) -> None:
	service = repo.get_service(service_id)
	if service is None:
		return
	async with URLChecker(max_concurrent=1) as checker:
		result = await recheck_service({"url": service.url, "timeout_s": service.timeout_s}, checker)
	ts = datetime.now(timezone.utc)
	repo.insert_check_result(
		service_id=service.id,
		ts=ts,
		ok=result.get("ok", False),
		status_code=result.get("status_code"),
		latency_ms=result.get("latency_ms"),
		error_text=(result.get("error_text") or ""),
	)
	# метрики
	try:
		record_check(service.id, ok=result.get("ok", False), status_code=result.get("status_code"), latency_value_ms=result.get("latency_ms"))
		ch_record(service.id, ts, ok=result.get("ok", False), status_code=result.get("status_code"), latency_ms=result.get("latency_ms"), error_text=(result.get("error_text") or ""))
	except Exception:
		pass
	# логика инцидентов
	last5 = repo.get_last_n_results(service_id, 5)
	open_inc = repo.get_open_incident(service_id)
	if result.get("ok"):
		if open_inc is not None:
			repo.close_incident(open_inc.id, datetime.now(timezone.utc))
			try:
				await notifier.send(
					AlertEvent(service_id=service_id, level="info", title="Инцидент закрыт", message="Сервис снова доступен")
				)
			except Exception:
				pass
		return
	# failure
	if open_inc is None:
		fails = 0
		for r in last5:
			if not r.ok:
				fails += 1
			else:
				break
		if fails >= 3:
			repo.open_incident(service_id, datetime.now(timezone.utc), fail_count=fails)
			try:
				await notifier.send(
					AlertEvent(service_id=service_id, level="error", title="Инцидент открыт", message="Сервис недоступен (3 ошибки подряд)")
				)
			except Exception:
				pass


from app.notifier import AlertEvent  # после определений классов, чтобы избежать циклических подсказок


@app.post("/services/{service_id}/recheck", response_model=RecheckResponse, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(api_key_auth)])
async def recheck(service_id: int = Path(ge=1)):
	service = repo.get_service(service_id)
	if service is None:
		raise HTTPException(status_code=404, detail="service not found")
	# если планировщик активен — кладём в его ручную очередь с приоритетом
	global _scheduler
	if _scheduler is not None:
		try:
			await _scheduler.enqueue_manual(service_id)
		except Exception:
			asyncio.create_task(_recheck_and_record(service_id))
	else:
		asyncio.create_task(_recheck_and_record(service_id))
	return RecheckResponse(queued=True)


@app.get("/incidents", response_model=List[IncidentListItem], dependencies=[Depends(rate_limit)])
async def list_incidents(is_open: bool = Query(True, alias="open")):
	items = repo.list_incidents(open_only=is_open)
	return [IncidentListItem(service_name=i.get("service_name"), start=i.get("start"), end=i.get("end")) for i in items]


@app.get("/incidents-page", include_in_schema=False)
async def incidents_page():
	return FileResponse(str(Path(_STATIC_DIR) / "incidents.html"))


@app.get("/ch-metrics")
async def ch_metrics():
	if not ch_has():
		raise HTTPException(status_code=404, detail="clickhouse disabled")
	p = ch_pctl(24)
	codes = ch_codes(24)
	return {"p50": p.get("p50"), "p95": p.get("p95"), "codes": codes} 