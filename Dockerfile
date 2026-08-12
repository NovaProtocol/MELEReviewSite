FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python3 -m compileall -q /app 2>/dev/null || true

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 7061

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "7061", "--workers", "1", "wsgi:app"]
