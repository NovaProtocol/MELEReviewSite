# Docker Infrastructure

## Compose Services (`compose.yaml`)

`name: melereview`

| Service | Build Context | Container | Expose | Publish | Healthcheck |
|---------|---------------|-----------|--------|---------|-------------|
| `melereview_api` | `.` / `api/Dockerfile` | `melereview_api` | `8082`, `50051` (gRPC) | none (via Caddy) | `python -c urllib.request.urlopen('http://127.0.0.1:8082/health')` |
| `melereview_web` | `.` / `web/Dockerfile` | `melereview_web` | `8081` | none (via Caddy) | `python -c urllib.request.urlopen('http://127.0.0.1:8081/health')` |
| `melereview_documentation` | `.` / `documentation/Dockerfile` | `melereview_documentation` | `8005` | none (via Caddy `handle_path /documentation/*`) | `python -c urllib.request.urlopen('http://127.0.0.1:8005/health')` |
| `caddy` | `./caddy` | `melereview_caddy` | `7060` | `127.0.0.1:7060:7060` | none (proxy) |
| `mysql-db` | `mysql:8.4` | `melereview_db` | `3306` | none | `mysqladmin ping -h localhost` (5s/5s/10) |

All app containers set `restart: unless-stopped`, `mem_limit`/`cpus` where needed, `DEPLOYMENT_TYPE` via `${DEPLOYMENT_TYPE:?}` fail-fast, and `depends_on: mysql-db condition: service_healthy` for DB consumers.

## Caddyfile (`caddy/Caddyfile`, `caddy:2-alpine`)

```caddyfile
:7060 {
    handle /health {
        reverse_proxy melereview_api:8082
    }

    handle /api/* {
        reverse_proxy melereview_api:8082
    }

    handle /static/* {
        header Cache-Control "public, max-age=31536000, immutable"
        forward_auth gatekeeper:7000 {
            uri /api/authz/forward-auth
        }
        reverse_proxy melereview_web:8081
    }

    handle_path /documentation/* {
        forward_auth gatekeeper:7000 {
            uri /api/authz/forward-auth
        }
        reverse_proxy melereview_documentation:8005
    }

    handle {
        forward_auth gatekeeper:7000 {
            uri /api/authz/forward-auth
        }
        reverse_proxy melereview_web:8081
    }
}
```

- `/health` bypasses `forward_auth` (public liveness).
- `handle /api/*` keeps the `/api` prefix (`handle`, not `handle_path`) for FastAPI's `APIRouter(prefix="/api")`.
- `handle_path /documentation/*` strips `/documentation` before proxying — MkDocs serves from `/`.
- Proxy targets use `container_name` (`melereview_api` etc.), never service name `app`, to avoid the `cloudflared-tunnel_default` shared-network DNS collision.
- Only Caddy publishes to the host, bound to `127.0.0.1:7060:7060`; gRPC `50051` is `expose:` only.

## Dockerfiles (`api/`, `web/`, `documentation/`)

Canonical `python:3.14-slim`, multi-stage `--prefix=/install`, `PYTHONDONTWRITEBYTECODE` + `PYTHONUNBUFFERED`, `pip --no-cache-dir`, `compileall`, `USER appuser --uid 10001`.

`api/Dockerfile`:

```dockerfile
FROM python:3.14-slim AS builder
WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /install /usr/local
COPY api/ ./api/
RUN python3 -m compileall -q /app 2>/dev/null || true
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8082
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8082", "--workers", "1", "api.app:app"]
```

`documentation/Dockerfile` adds `mkdocs build` between copy and `useradd`, then `granian --port 8005 app:app`.

## MySQL

`mysql:8.4`, named volume `mysql_data:/var/lib/mysql`, `command: --max_connections=200`, `TEXT` columns use `default="[]"` not `server_default` (MySQL 8.4 `TEXT` pitfall). Adaptive migrations wrap `ALTER TABLE` with `SET FOREIGN_KEY_CHECKS=0/1` on the same connection and guard `MODIFY COLUMN` shrinks via `func.char_length`.

## Networks

```yaml
networks:
  default:
  gatekeeper:
    external: true
    name: gatekeeper_default
  cloudflared-tunnel:
    external: true
    name: cloudflared-tunnel_default
```

Only `caddy` joins `gatekeeper` + `cloudflared-tunnel`; app containers stay on `default`, gRPC stays `expose:`-only and is reachable as `melereview_api:50051` on the internal network.

## Verification

```bash
docker compose build documentation
mkdocs build --strict  # in documentation/
curl http://documentation:8005/health  # from sibling container
curl -i https://<host>/documentation/  # via Caddy, renders Material theme
```
