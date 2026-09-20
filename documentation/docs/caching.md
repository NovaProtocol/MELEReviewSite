# Caching

Three services in this stack set `Cache-Control`, and two separate layers are
involved: the app's own middleware, and one `Caddyfile` rule for `/static/*`. This
page states which layer owns which response, what the values are, and why the
`DEPLOYMENT_TYPE` variable is absent from two of the three services on purpose.

## The rule

> A response may be `public`-cacheable only when the path is ungated (the gate
> resolved `action == "none"`) and the upstream chose that header itself.

GateKeeper is the gate for this site. It demotes any shared-cacheable value on a
response it produced or on a proxied response whose request it decided, and it
leaves the ungated `action == "none"` pass-through alone. That demotion is what
makes the rest of this page safe, and it happens before the response reaches
Cloudflare, which is a shared cache keyed on the URL alone.

## Where the policy lives

| Service | File | `DEPLOYMENT_TYPE` in compose | Behaviour |
|---------|------|------------------------------|-----------|
| `melereview_api` | `api/cache.py` | yes (`debug`) | debug: fills `no-store` on responses with no header; production: fills per path class |
| `melereview_web` | `web/cache.py` | **absent** | `is_debug_deployment()` returns `False`, so it fills production values |
| `melereview_documentation` | `documentation/cache.py` | **absent** | same, production values |

`api/cache.py` and `web/cache.py` are duplicated on purpose and must stay
byte-identical apart from the marker comment in the API copy. A test asserts it.

The middleware decides in this order:

1. **An existing header is kept.** If the response already carries
   `Cache-Control`, it is returned untouched.
2. **A gap is filled.** Only when the response carries none does the middleware
   write a value: `no-store` in debug, the path class's lifespan otherwise.

`is_debug` decides *what value is filled in*. It never decides whether an existing
value is overwritten. Before this rule was fixed, the debug branch assigned
`no-store` unconditionally, which pinned every asset on the deployment to no
caching at all.

## Values

| Class | Paths | Debug | Production |
|-------|-------|-------|------------|
| API | `/api/` | `no-store` | `private, no-store` |
| Static | `/static/` | `no-store` | `public, max-age=86400` |
| Health | `/health` | `no-store` | `public, max-age=3600` |
| HTML | anything unmatched | `no-store` | `private, max-age=300` |

The API prefix is tested before the health list, so `/api/health` is
`private, no-store` and the `"/api/health"` entry in `_MISC_PATHS` never reaches
its own branch. Point a monitor at `/health`.

The constants live at the top of each copy and are deliberately not environment
variables: four integers do not justify new required config, and a redeploy is
the honest way to change them.

## Why `melereview_web` has no `DEPLOYMENT_TYPE`

`is_debug_deployment()` reads `os.environ.get("DEPLOYMENT_TYPE", "")` and returns
`False` when the value is absent, so a service with no variable takes the
production branch. That is exactly what gives `/static` its day-long lifespan.

The variable is set on `melereview_api` alone (line 11 of `compose.yaml`). An
earlier version of the Docker page claimed it was passed fail-fast to every app
container, which was never true for these two. Adding `DEPLOYMENT_TYPE=debug` to
`melereview_web` or `melereview_documentation` would flip every response they fill
to `no-store`, which is the opposite of the intent, so the absence is deliberate.
An empty value read locally would fall back to a debug default if a service read
it differently, so check `is_debug_deployment()` rather than the environment when
reasoning about this.

## The Caddy rule for `/static/*`

`caddy/Caddyfile` carries one cache rule, in the `/static/*` handle:

```caddy
handle /static/* {
    header >Cache-Control "public, max-age=31536000, immutable"
    reverse_proxy melereview_web:8081
}
```

Two details are load-bearing:

- **`>` replaces.** A bare `header Cache-Control "…"` **adds** a second
  `Cache-Control` line, it does not replace the one the app sent, and the app
  sets `public, max-age=86400` for `/static/`. The response used to leave with two
  values, which is a defect: a cache has to guess which one wins. `header
  >Cache-Control` replaces the app's value with the edge's longer lifespan, so
  exactly one value leaves.
- **The `reverse_proxy` must stay in the same block.** A `handle` that only sets a
  header still wins the route and returns an **empty `200`**, it does not fall
  through to the catch-all. The proxy line and the header belong together.

The asserted substring is unchanged, so the Caddyfile test keeps passing.

## Verifying a change

Read the headers from the running stack rather than from the source:

```bash
curl -sI http://127.0.0.1:7060/static/js/question_form.js | grep -i cache-control
```

Exactly one `Cache-Control` line should come back, with the one-year lifespan
from the Caddy rule. Two lines mean the replace form was lost. Without the Caddy
rule in front, the app's `public, max-age=86400` is what a static path carries.
