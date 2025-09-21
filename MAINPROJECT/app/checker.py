import asyncio          
import aiohttp          
import logging        
import os            
import random        
from aiohttp.client_exceptions import ClientConnectorCertificateError
import ssl

from typing import TypedDict, Optional, NotRequired, Type
from time import perf_counter
from types import TracebackType

logger = logging.getLogger(__name__)

class Service(TypedDict):
    url: str          
    timeout_s: int    

class CheckResult(TypedDict):
    ok: bool                             
    status_code: NotRequired[Optional[int]] 
    latency_ms: NotRequired[Optional[int]]  
    error_text: NotRequired[Optional[str]]  
    # Дополнительные фазы (best-effort)
    dns_ms: NotRequired[Optional[int]]
    connect_ms: NotRequired[Optional[int]]
    tls_ms: NotRequired[Optional[int]]
    ttfb_ms: NotRequired[Optional[int]]

class URLChecker:
    def __init__(self, max_concurrent: int = 5,
                connect_timeout_s: float = 3.0,
                user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PingTower/1.0"):
        if (not isinstance(max_concurrent, int) or max_concurrent < 1):
            raise ValueError("max_concurrent должен быть целым числом >= 1")
            
        self._max_concurrent = max_concurrent
        self._connect_timeout_s = connect_timeout_s
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._user_agent = user_agent
        self._trace: Optional[aiohttp.TraceConfig] = None
        self._timings: dict[str, float] = {}
        
    async def __aenter__(self):
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        # TraceConfig для фаз
        self._trace = aiohttp.TraceConfig()
        async def _dns_start(session, context, params):
            self._timings['dns_start'] = perf_counter()
        async def _dns_end(session, context, params):
            self._timings['dns_end'] = perf_counter()
        async def _conn_start(session, context, params):
            self._timings['conn_start'] = perf_counter()
        async def _conn_end(session, context, params):
            self._timings['conn_end'] = perf_counter()
        async def _tls_start(session, context, params):
            self._timings['tls_start'] = perf_counter()
        async def _tls_end(session, context, params):
            self._timings['tls_end'] = perf_counter()
        async def _req_start(session, context, params):
            self._timings['req_start'] = perf_counter()
        async def _resp_headers(session, context, params):
            self._timings['resp_headers'] = perf_counter()
        self._trace.on_dns_resolvehost_start.append(_dns_start)
        self._trace.on_dns_resolvehost_end.append(_dns_end)
        self._trace.on_connection_create_start.append(_conn_start)
        self._trace.on_connection_create_end.append(_conn_end)
        self._trace.on_request_start.append(_req_start)
        # tls callbacks доступны на TCP, fallback через conn timings
        try:
            self._trace.on_ssl_conn_start.append(_tls_start)  # type: ignore
            self._trace.on_ssl_conn_end.append(_tls_end)  # type: ignore
        except Exception:
            pass
        self._trace.on_response_headers.append(_resp_headers)
        # Создаём сессию без дефолтного таймаута, будем задавать в каждом запросе
        self._session = aiohttp.ClientSession(
            headers={"User-Agent": self._user_agent},
            trace_configs=[self._trace]
        )
        return self
    
    async def __aexit__(
        self, 
        exc_type: Optional[Type[BaseException]], 
        exc_val: Optional[BaseException], 
        exc_tb: Optional[TracebackType]
    ) -> None:
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                logger.warning(f"Failed to close session: {e}")
        self._semaphore = None
        self._session = None
        self._trace = None
        self._timings.clear()
    
    # Переводим в миллисекунды задержку
    def calculate_latency_ms(self, start_time: float) -> int:
        return int((perf_counter() - start_time) * 1000)

    def _extract_phase_timings(self) -> dict[str, int|None]:
        def diff(a: str, b: str) -> Optional[int]:
            if a in self._timings and b in self._timings:
                return int((self._timings[b] - self._timings[a]) * 1000)
            return None
        return {
            'dns_ms': diff('dns_start', 'dns_end'),
            'connect_ms': diff('conn_start', 'conn_end'),
            'tls_ms': diff('tls_start', 'tls_end'),
            'ttfb_ms': diff('req_start', 'resp_headers'),
        }

    async def check_url(self, url: str, timeout_s: int) -> CheckResult:
        # Логика таймаутов
        connect = min(self._connect_timeout_s, timeout_s) 
        read = max(timeout_s - connect, 1)
        timeout = aiohttp.ClientTimeout(connect=connect, total=connect + read)
        
        start_pre = perf_counter()
        
        # Параметры ретраев
        max_attempts = max(1, int(os.getenv("HTTP_RETRY_ATTEMPTS", "1")))
        base_backoff_ms = max(50, int(os.getenv("HTTP_RETRY_BASE_MS", "200")))
        backoff_jitter_ms = max(0, int(os.getenv("HTTP_RETRY_JITTER_MS", "100")))
        
        try:
            if (self._semaphore is None):
                raise RuntimeError("URLChecker должен использоваться внутри 'async with' блока")
            
            attempt = 0
            last_exception: Optional[Exception] = None
            while attempt < max_attempts:
                attempt += 1
                async with self._semaphore:
                    start_in = perf_counter()
                    
                    if (self._session is None):
                        raise RuntimeError("URLChecker должен использоваться внутри 'async with' блока")

                    if (not isinstance(timeout_s, int) or timeout_s < 1):
                        raise ValueError("timeout_s должен быть целым числом >= 1")
                    
                    ssl_verify = os.getenv("HTTP_SSL_VERIFY", "true").lower() not in ("0", "false", "no")
                    try:
                        # Поддержка кастомного CA: если указан путь в HTTP_CA_BUNDLE и verify=true
                        ssl_param = ssl_verify
                        ca_bundle = os.getenv("HTTP_CA_BUNDLE")
                        if ssl_verify and ca_bundle:
                            try:
                                ctx = ssl.create_default_context(cafile=ca_bundle)
                                ssl_param = ctx
                            except Exception:
                                ssl_param = ssl_verify
                        async with self._session.get(url, timeout=timeout, ssl=ssl_param) as response:
                            latency_ms = self.calculate_latency_ms(start_in)
                            status_code = response.status
                            phases = self._extract_phase_timings()
                            if (200 <= status_code < 400):
                                return {"ok": True, "status_code": status_code, "latency_ms": latency_ms, **phases, "error_text": None}
                            # 4xx/5xx не ретраим 4xx
                            if 400 <= status_code < 500:
                                return {"ok": False, "status_code": status_code, "latency_ms": latency_ms, **phases, "error_text": None}
                            # 5xx можно ретраить
                            if attempt >= max_attempts:
                                return {"ok": False, "status_code": status_code, "latency_ms": latency_ms, **phases, "error_text": None}
                    except (aiohttp.ClientSSLError, ClientConnectorCertificateError) as e_ssl:
                        insecure_retry = os.getenv("HTTP_SSL_INSECURE_RETRY", "true").lower() in ("1", "true", "yes")
                        if insecure_retry and ssl_verify:
                            try:
                                async with self._session.get(url, timeout=timeout, ssl=False) as response:
                                    latency_ms = self.calculate_latency_ms(start_in)
                                    status_code = response.status
                                    phases = self._extract_phase_timings()
                                    if (200 <= status_code < 400):
                                        return {"ok": True, "status_code": status_code, "latency_ms": latency_ms, **phases, "error_text": None}
                                    if 400 <= status_code < 500:
                                        return {"ok": False, "status_code": status_code, "latency_ms": latency_ms, **phases, "error_text": None}
                                    if attempt >= max_attempts:
                                        return {"ok": False, "status_code": status_code, "latency_ms": latency_ms, **phases, "error_text": None}
                            except Exception:
                                last_exception = e_ssl
                        else:
                            last_exception = e_ssl
                    except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                        last_exception = e
                # backoff перед следующей попыткой, если не последняя
                if attempt < max_attempts:
                    delay_ms = base_backoff_ms * (2 ** (attempt - 1)) + random.randint(0, backoff_jitter_ms)
                    try:
                        await asyncio.sleep(delay_ms / 1000.0)
                    except Exception:
                        pass
            # Все попытки исчерпаны — возвращаем ошибку
            latency_ms = self.calculate_latency_ms(start_in if 'start_in' in locals() else start_pre)
            phases = self._extract_phase_timings()
            if isinstance(last_exception, asyncio.TimeoutError):
                return {"ok": False, "status_code": None, "latency_ms": latency_ms, **phases, "error_text": "Timeout"}
            if isinstance(last_exception, (aiohttp.ClientSSLError, ClientConnectorCertificateError)):
                return {"ok": False, "status_code": None, "latency_ms": latency_ms, **phases, "error_text": "SSL error"}
            if isinstance(last_exception, aiohttp.ClientError):
                return {"ok": False, "status_code": None, "latency_ms": latency_ms, **phases, "error_text": (str(last_exception) or "Client error")[:512]}
            return {"ok": False, "status_code": None, "latency_ms": latency_ms, **phases, "error_text": (str(last_exception) or "Unexpected error")[:512]}
        
        except asyncio.TimeoutError:
            latency_ms = self.calculate_latency_ms(start_in if 'start_in' in locals() else start_pre)
            return {
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "error_text": "Timeout"
            }
        
        except aiohttp.ClientConnectorError as e_ClientConnector:
            latency_ms = self.calculate_latency_ms(start_in if 'start_in' in locals() else start_pre)
            error_text = (str(e_ClientConnector) or "Connection error")[:512]
            return {
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "error_text": error_text
            }
        
        except aiohttp.ClientSSLError as e_ClientSSLError:
            latency_ms = self.calculate_latency_ms(start_in if 'start_in' in locals() else start_pre)
            error_text = (str(e_ClientSSLError) or "SSL error")[:512]
            return {
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "error_text": error_text
            }
        
        except aiohttp.ClientError as e_ClientError:
            latency_ms = self.calculate_latency_ms(start_in if 'start_in' in locals() else start_pre)
            error_text = (str(e_ClientError) or "Client error")[:512]
            return {
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "error_text": error_text
            }
        
        except Exception as e:
            latency_ms = self.calculate_latency_ms(start_in if 'start_in' in locals() else start_pre)
            error_text = (f"Unexpected error: {str(e)}" or "Unexpected error")[:512]
            return {
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "error_text": error_text
            }

async def recheck_service(service: Service, checker: URLChecker) -> CheckResult:
    # Проверяем наличие обязательных полей
    if ("url" not in service or "timeout_s" not in service):
        logger.error("Неправильный формат service: отсутствуют обязательные поля")
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": None,
            "error_text": "Неправильный формат service: отсутствуют url или timeout_s"
        }
    
    url = service["url"]
    timeout_s = service["timeout_s"]
    
    # Улучшенная валидация URL
    if (not isinstance(url, str)
        or not url.strip() 
        or not url.startswith(("http://", "https://"))):
        logger.error(f"Неправильный URL формат: {url}")
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": None,
            "error_text": "Неправильный URL формат"
        }
    
    # Валидация таймаута
    if (not isinstance(timeout_s, int) or timeout_s <= 0):
        logger.error(f"Неправильный таймаут: {timeout_s}")
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": None,
            "error_text": "Таймаут должен быть положительным целым числом"
        }
    
    # Логируем начало проверки
    logger.info(f"Начинаем проверку: {url}")
    
    # Вызываем метод check_url объекта checker
    result = await checker.check_url(url, timeout_s)
    
    if result["ok"]:
        logger.info(f"Успешная проверка {url}: {result['status_code']}")
    else:
        logger.error(f"Ошибка при проверке {url}: {result.get('error_text')}")
    
    return result