## Task 9: Frontend Infra Fix — base.html DOM race, Caddy caching

### Changes

1. **`web/templates/base.html`**
   - Added `defer` to all CDN scripts in `<head>` (jQuery, mathquill, mathjs) to avoid blocking parse.
   - Removed inline `getElementById("dark-mode-toggle").checked=...` that ran before `<nav>` existed (null error). Early script now only sets `document.body.className` from localStorage (FOUC prevention).
   - Moved `applyTheme` definition inside `DOMContentLoaded` handler and added null guard `if (toggle)`. Ensures `getElementById("dark-mode-toggle")` only executes after DOM is ready. Test `split("DOMContentLoaded")[0]` now passes.

2. **`caddy/Caddyfile`**
   - Replaced `no-cache, no-store, must-revalidate` + `Pragma`/`Expires` with `Cache-Control "public, max-age=31536000, immutable"` for `/static/*`.
   - Kept `forward_auth` for `/static/*` and preserved `handle /health` bypass without auth.

3. **`web/static/js/questions.js` / `web/static/css/main.css`**
   - No changes required: `questions.js` already has debounced search and `DOMContentLoaded` logging; `main.css` already contains `.q-blocks` styles (715 lines split retained).

4. **`tests/test_frontend_infra.py`** (new)
   - `test_base_no_dom_race` — asserts no `getElementById("dark-mode-toggle")` before first `DOMContentLoaded`.
   - `test_base_has_defer` — asserts `defer` present.
   - `test_caddy_static_cached` — asserts public immutable Cache-Control and no `no-cache`.
   - `test_caddy_health_bypass` — asserts `/health` handle has no `forward_auth`.

### Tests

- Created failing tests, verified 3 failures, fixed, then PASS:
  - `uv run pytest tests/test_frontend_infra.py -v` → 4 passed
  - `uv run pytest -v` → 54 passed, 0 failed

### Commit

- `fix: move theme init to DOMContentLoaded, cache static assets` (includes base.html, Caddyfile, test)
