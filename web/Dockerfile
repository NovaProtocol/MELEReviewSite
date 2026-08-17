FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web/ ./web/

EXPOSE 8081

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8081", "--workers", "1", "web.app:app"]
