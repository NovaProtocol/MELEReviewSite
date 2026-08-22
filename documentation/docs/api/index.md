# API Reference

Base URL via Caddy: `http://127.0.0.1:7060/api` → `reverse_proxy melereview_api:8082`. All responses include `X-Request-ID` (propagated or generated). Every list endpoint returns `X-Total-Count`.

Auth: session cookie `session` (signed `itsdangerous.URLSafeSerializer(SECRET_KEY)`), `httponly, samesite=lax, secure=!DEBUG, max_age 30d`. `get_current_account` dependency → `401` when missing/invalid/disabled.

## Auth

| Method | Path | Auth | Body / Response |
|--------|------|------|-----------------|
| `GET` | `/api/auth/accounts` | none | `AccountOut[]` |
| `POST` | `/api/auth/accounts` | rate-limited `5/minute` | `{name,pin}` → `201 AccountOut` + `Location`; `409` on duplicate |
| `POST` | `/api/auth/login` | `5/minute` | `{account_id,pin}` → sets `session` cookie `{id,name}` |
| `POST` | `/api/auth/logout` | cookie | clears cookie |
| `GET` | `/api/auth/me` | cookie | `AccountOut` |
| `DELETE` | `/api/auth/me` | cookie | soft-disable (`disabled=true`) → `204` |

## Questions

See [Questions](../questions/index.md).

| Method | Path | Auth |
|--------|------|------|
| `GET` | `/api/questions` | none |
| `GET` | `/api/questions/{id}` | none |
| `POST` | `/api/questions` | cookie |
| `PUT` | `/api/questions/{id}` | owner/admin |
| `DELETE` | `/api/questions/{id}` | owner/admin |
| `POST` | `/api/questions/{id}/flag` | cookie |
| `GET` | `/api/tags` | none |

## Solutions (Blocks)

See [Blocks](../blocks/index.md).

| Method | Path | Auth |
|--------|------|------|
| `GET` | `/api/questions/{id}/solution` | cookie (own) |
| `PUT` | `/api/questions/{id}/solution` | cookie |
| `GET` | `/api/my/solutions` | cookie |
| `GET` | `/api/questions/{id}/solutions` | — |

## Thermo

| Method | Path | Auth |
|--------|------|------|
| `POST` | `/api/cycle?format=data\|plot` | none (public) |

## Health

| Method | Path | Auth |
|--------|------|------|
| `GET` | `/health` | none (public, bypasses GateKeeper) → `{"status":"ok"}` |

## gRPC Contract (internal `melereview_api:50051`)

Proto location: `proto/question.proto` (package `api.v1`). Generated stubs: `api/proto_gen/` and `web/proto_gen/` (both import the same `*_pb2.py`). Build:

```bash
python -m grpc_tools.protoc -I proto --python_out=api/proto_gen --grpc_python_out=api/proto_gen proto/question.proto
python -m grpc_tools.protoc -I proto --python_out=web/proto_gen --grpc_python_out=web/proto_gen proto/question.proto
```

Key packages:

```protobuf
syntax = "proto3";
package api.v1;

service QuestionService { ... }
service SolutionService { ... }
service ThermoService { rpc SolveCycle ... } // optional
```

- Server: `grpc.aio.server` on `0.0.0.0:50051` started in `api/app.py` `lifespan` (await `server.start()`; `stop(grace=5)` on shutdown). Registered via `api_pb2_grpc.add_QuestionServiceServicer_to_server`.
- Client: `grpc.aio.insecure_channel("melereview_api:50051")` from `web/grpc_client.py`. Example:

```python
from web.grpc_client import get_question_via_grpc

resp = await get_question_via_grpc(42)
# raises grpc.aio.AioRpcError with NOT_FOUND when missing
```

- Errors: servicer uses `await context.set_code(grpc.StatusCode.NOT_FOUND)` / `INVALID_ARGUMENT` etc.; HTTP edge maps to `404/400/409` — never leak `RpcError` to HTTP clients.
- Network: `expose: ["50051"]` only, never `ports:`; Caddy does **not** proxy gRPC; public traffic stays on `handle /api/*` HTTP.
- Proto versioning: `package api.v1` aligned with HTTP `/api`; breaking change bumps to `v2`.

When no server-side container-to-container call exists (current shape: browser `fetch("/api/...")` via Caddy), the gRPC server is scaffolding — internal, documented, and available for future `web` SSR or a `worker` that needs tight RPC.

## OpenAPI

FastAPI serves `/openapi.json` and `/docs` (Swagger) from the API container (`api:8082`). Caddy does not strip the prefix, so `GET /api/openapi.json` is **not** a route — use `GET http://127.0.0.1:7060/docs` via `melereview_api:8082` if you port-forward, or reach the API container directly on the compose network.
