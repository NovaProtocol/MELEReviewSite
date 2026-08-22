FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY documentation/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY documentation/ /app/

RUN mkdocs build

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

RUN python3 -m compileall -q /app 2>/dev/null || true

EXPOSE 8005

USER appuser

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8005", "--workers", "1", "app:app"]
