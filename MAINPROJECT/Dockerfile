# Сборочный образ (builder)
FROM python:3.11-slim as builder
ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1
RUN apt-get update \
	&& apt-get install -y --no-install-recommends build-essential curl \
	&& rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt /build/requirements.txt
RUN pip wheel --no-cache-dir --no-deps -r /build/requirements.txt -w /build/wheels

# Рантайм-образ (похоже на distroless slim)
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir /wheels/* \
	&& rm -rf /wheels
COPY app/ /app/app/
COPY README.md /app/README.md
# Пользователь без прав root
RUN useradd -ms /bin/bash appuser \
	&& chown -R appuser:appuser /app
USER appuser
# ФС только для чтения с доступной для записи /tmp
VOLUME ["/tmp"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 