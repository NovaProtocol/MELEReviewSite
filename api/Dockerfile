FROM python:3.14-slim AS builder

WORKDIR /app

COPY api/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /install /usr/local
COPY api/ ./api/

# Generate gRPC stubs from proto (container-to-container internal)
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. api/proto/api.proto || echo "protoc fallback: stubs not generated"

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8082
EXPOSE 50051

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8082", "--workers", "1", "api.app:app"]
