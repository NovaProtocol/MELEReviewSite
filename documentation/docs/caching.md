# Caching

One middleware, `app/cache.py`, sets `Cache-Control` on every response. One Caddy rule lengthens the
lifespan for `/static/*`.

## The rule

> A response may be shared-cacheable only when the path is ungated and the upstream chose that
> header itself.

GateKeeper demotes anything shared-cacheable on a response it produced or decided, and leaves an
ungated pass-through alone. This app sits behind it, and it does not need to know which paths are
gated: every page here is per-visitor anyway, so the app's own policy is `private`.

## Precedence

1. **Debug caches nothing.** With `DEPLOYMENT_TYPE=debug`, any value that is not already
   `private` or `no-store` is replaced with `no-store`. A value that already forbids storage is kept
   verbatim, so the gate's own verdict survives.
2. **Production keeps an existing header.** If a route set `Cache-Control` itself, it is returned
   untouched.
3. **Production fills a gap** by path class.

## Values

| Class | Paths | Debug | Production |
|---|---|---|---|
| Static | `/static/` | `no-store` | `public, max-age=86400` |
| Health | `/health` | `no-store` | `public, max-age=3600` |
| API | `/api/` | `no-store` | `private, no-store` |
| Media | `/media/` | `no-store` | `private, no-store` |
| HTML | everything else | `no-store` | `private, no-store` |

HTML moved from `private, max-age=300` to `private, no-store` when the site became account-based.
A library page differs per visitor now, so giving it a five-minute private lifespan means a member
who fixes an attempt sees a stale count. Nothing on this site is worth caching except the assets.

`/media/*` is grouped with the API deliberately: an avatar or a solution image belongs to one
visitor's session and must not sit in a shared cache. The route also sets the header itself, so the
middleware leaves it alone.

## The Caddy rule

```caddy
handle /static/* {
	header >Cache-Control "public, max-age=31536000, immutable"
	reverse_proxy melereview_main:7061
}
```

- **`>` replaces.** A bare `header Cache-Control "…"` adds a second line instead of replacing the
  one the app sent. `header >Cache-Control` leaves exactly one value on the response, replacing the
  app's `public, max-age=86400` with the edge's longer lifespan. This is why hashed assets are safe
  to pin for a year: a change ships under a new `?v=`.
- **The `reverse_proxy` stays in the same block.** A `handle` that only sets a header still wins
  the route and answers an empty `200`; it does not fall through to the catch-all.

## Verifying a change

Read the headers from the running stack, not the source:

```bash
curl -sI http://127.0.0.1:7060/static/css/main.css | grep -i cache-control
curl -sI http://127.0.0.1:7060/library | grep -i cache-control
```

Exactly one `Cache-Control` line should come back for each. Two lines on a static asset means the
replace form was lost.

`tests/test_cache_headers.py` asserts the precedence in both modes, the per-visitor classification
for `/api/`, `/media/` and HTML, and that an absent `DEPLOYMENT_TYPE` reads as production.
