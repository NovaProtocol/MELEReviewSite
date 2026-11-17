# 0001 — Secrets, forms, and the administrator password

Status: accepted (2026-11-17)

## Context

Two ways a credential can leave this app without anyone noticing:

1. A `<form>` with no `method` submits a GET. Any script that has not loaded turns
   the field values into a query string. That puts a password in the address bar,
   in browser history, in the `Referer` header, and in the access log of every hop.
2. `ADMIN_PASS` defaults to the documented example, and the boot reconciles the
   administrator row from it on every start. A deployment that never changed the
   example therefore has a published master key that survives every restart.

Both were true here. The first is a defect; the second is a default that is safe
only if nobody forgets.

## Decision

- Every form names its `method` explicitly and points at the endpoint it belongs to.
  `tests/test_forms.py` walks every template and fails if a bare `<form>` appears.
- A non-debug boot **refuses to start** while `ADMIN_PASS` is a shipped example
  value. Debug warns. Rotating the password is still one environment change,
  because the boot applies it.
- Endpoints that consume a JSON body stay JSON-only, so a native submit is refused
  rather than half-accepted.

## Consequences

- A production deployment that upgrades onto this build stops and asks for a
  password instead of starting with the default. That is intentional: the failure
  is loud, immediate, and names the fix.
- Local debug work is unchanged, because `DEPLOYMENT_TYPE=debug` warns.

## Verification

`tests/test_forms.py`, `tests/test_config.py`, and a browser check that blocks
`auth.js` and submits the login form natively: the URL afterwards is
`/api/auth/login`, with no query string.
