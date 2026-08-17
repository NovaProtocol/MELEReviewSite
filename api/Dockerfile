FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/

EXPOSE 8082

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8082", "--workers", "1", "api.app:app"]
