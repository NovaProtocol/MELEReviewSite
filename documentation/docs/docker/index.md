# Docker Infrastructure

## Compose services

`name: melereview`

| Service | Build | Container | Port | Published |
|---|---|---|---|---|
| `melereview_main` | root `Dockerfile` | `melereview_main` | 7061 | no, internal |
| `melereview_documentation` | `documentation/Dockerfile` | `melereview_documentation` | 8005 | no, internal |
| `caddy` | `caddy/Dockerfile` | `melereview_caddy` | 7060 | `127.0.0.1:7060` |
| `mysql-db` | `mysql:8.4` | `melereview_db` | 3306 | no, internal |

Every service is `restart: unless-stopped`. `melereview_main` waits on
`mysql-db: condition: service_healthy` and declares a `/health` healthcheck on 7061 with a 20-second
start period, because the first boot creates the schema and runs the seed.

Volumes: `mysql_data` at `/var/lib/mysql`, `uploads_data` at `/app/uploads`. No bind mounts.

## Ports

Caddy owns the block's base port and the app listens on base+1:

| Port | Owner |
|---|---|
| 7060 | `melereview_caddy`, loopback publish |
| 7061 | `melereview_main` |
| 8005 | `melereview_documentation` |

## Environment

Required with fail-fast interpolation in `compose.yaml`:

```yaml
DEPLOYMENT_TYPE: ${DEPLOYMENT_TYPE:?DEPLOYMENT_TYPE is required}
MYSQL_PASS: ${MYSQL_PASS:?MYSQL_PASS is required}
SECRET_KEY: ${SECRET_KEY:?SECRET_KEY is required}
ADMIN_USER: ${ADMIN_USER:?ADMIN_USER is required}
ADMIN_PASS: ${ADMIN_PASS:?ADMIN_PASS is required}
```

Optional with defaults:

```yaml
MYSQL_USER: ${MYSQL_USER:-root}
MYSQL_DATABASE: ${MYSQL_DATABASE:-MELEReview}
UPLOAD_DIR: /app/uploads
MAX_UPLOAD_BYTES: ${MAX_UPLOAD_BYTES:-8388608}
MAX_OPEN_INVITES: ${MAX_OPEN_INVITES:-5}
COOKIE_SECURE: ${COOKIE_SECURE:-}
```

There is one app container now. The previous build set `DEPLOYMENT_TYPE` on the API service only and
explained that the web service therefore took the production branch; that split no longer exists, so
the variable reaches every response this stack serves.

## Caddyfile

```caddy
:7060 {
	header {
		-Server
		X-Content-Type-Options nosniff
		Referrer-Policy strict-origin-when-cross-origin
		X-Frame-Options SAMEORIGIN
	}

	handle /tools/* {
		header >X-Frame-Options "SAMEORIGIN"
		reverse_proxy melereview_main:7061
	}

	handle /health {
		reverse_proxy melereview_main:7061
	}

	handle /api/* {
		reverse_proxy melereview_main:7061
	}

	handle /media/* {
		reverse_proxy melereview_main:7061
	}

	handle /static/* {
		header >Cache-Control "public, max-age=31536000, immutable"
		reverse_proxy melereview_main:7061
	}

	handle_path /documentation/* {
		reverse_proxy melereview_documentation:8005
	}

	handle {
		reverse_proxy melereview_main:7061
	}
}
```

- Every target is `melereview_main:7061`, a `container_name`, never the service name `app`. The
  `gatekeeper` network is shared across projects and a generic name resolves to every container that
  carries it.
- `header >Cache-Control` **replaces** the app's value rather than adding a second line, and the
  `reverse_proxy` stays in the same block: a `handle` holding only a `header` still wins the route
  and answers an empty `200`.
- `handle_path /documentation/*` strips the prefix, because MkDocs serves from `/`.
- `/tools/*` is proxied to the app so the rail's iframe can load a tool page from the same origin.
  The `SAMEORIGIN` frame header is re-asserted there.
- No `forward_auth`. Gating is GateKeeper's decision, made before traffic reaches this Caddy.

## Dockerfile

`python:3.14-slim`, two stages, dependencies installed before source:

```dockerfile
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
COPY mysql/ ./mysql/
COPY wsgi.py ./
RUN python3 -m compileall -q /app 2>/dev/null || true
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/uploads \
    && chown -R appuser:appuser /app
USER appuser
EXPOSE 7061
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "7061", "--workers", "1", "wsgi:app"]
```

`mysql/` is copied because `app/bootstrap.py` executes `mysql/seed/taxonomy.sql` from the image.
`/app/uploads` is created and owned by `appuser` so the named volume mounts onto a writable
directory.

## MySQL

`mysql:8.4`, `--max_connections=200`, `--max_allowed_packet=16M`, healthcheck
`mysqladmin ping` at 5s with 10 retries.

Two rules the schema honours:

- **No `server_default` on `TEXT`.** MySQL 8.4 rejects a default on `TEXT` and `BLOB`. The text
  columns carry a Python-side default or nothing at all.
- **`FOREIGN_KEY_CHECKS=0` around adaptive DDL.** The schema pass creates missing tables and adds
  missing columns with the checks off, then restores them.

## Networks

```yaml
networks:
  default:
  gatekeeper:
    external: true
    name: gatekeeper
```

Only `caddy` joins `gatekeeper`. The app, MySQL and the documentation service stay on `default`. No
container joins `cloudflared-tunnel`: the tunnel reaches GateKeeper's Caddy, and GateKeeper proxies
here.

## Verification

```bash
docker compose ps
curl -s http://127.0.0.1:7060/health
docker logs melereview_main | head -20         # legacy reset, seed count, administrator
docker exec melereview_main id                 # uid=10001(appuser)
curl -sI http://127.0.0.1:7060/static/css/main.css | grep -i cache-control
```
