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
- **The administrator has no stored password hash.** The password is `ADMIN_PASS`
  and is compared in memory at sign-in. The users table keeps `NULL` for that
  account, and a hash planted in it is ignored, so a database dump yields no usable
  administrator credential.
- Endpoints that consume a JSON body stay JSON-only, so a native submit is refused
  rather than half-accepted.

## Consequences

- The administrator cannot change its password in the interface; the app answers
  409 and points at `ADMIN_PASS`. Changing the environment and restarting is the
  only way, which is the same operation either way.
- A database-only restoration cannot recover administrator access: the environment
  must supply the password. That is the point.
- Nothing refuses to boot: the deployment starts with whatever `ADMIN_PASS` holds.

## Verification

`tests/test_forms.py`, `tests/test_config.py`, and a browser check that blocks
`auth.js` and submits the login form natively: the URL afterwards is
`/api/auth/login`, with no query string.
