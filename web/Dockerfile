FROM python:3.14-slim AS builder

WORKDIR /app

COPY web/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /install /usr/local
COPY web/ ./web/
COPY api/proto/ ./api/proto/

# Generate gRPC stubs for client (optional, fallback if protoc fails)
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. api/proto/api.proto || echo "protoc fallback: stubs not generated"

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8081

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8081", "--workers", "1", "web.app:app"]
