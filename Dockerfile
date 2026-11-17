FROM node:22-slim AS client

WORKDIR /client
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
# The build writes into the Python tree, so the copied path is relative to it.
RUN npm run build

FROM python:3.14-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /install /usr/local
COPY app/ ./app/
COPY --from=client /app/static/app ./app/static/app
COPY mysql/ ./mysql/
COPY wsgi.py ./

RUN python3 -m compileall -q /app 2>/dev/null || true

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/uploads \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 7061

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "7061", "--workers", "1", "wsgi:app"]
