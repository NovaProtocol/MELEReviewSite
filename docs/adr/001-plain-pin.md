# ADR 001: Plain PIN Storage (Netflix-style)

**Status:** Accepted
**Date:** 2026-08-21
**Context:** MELE Review is a low-value personal tool for board-exam review.
Deciders: project owners.

## Context

MELE Review uses a Netflix-style account picker: create a profile (name + 4-digit
PIN), then log in by selecting the profile and entering its PIN. The app is a
personal/family tool, not a high-value internet-facing service. Accounts guard
per-user solutions and question progress, not sensitive data or payments.

Early design considered bcrypt-hashed PINs. However:

- PINs are short (4 digits, ~10k entropy), hashing does not add meaningful
  protection against brute force if DB leaks; the attacker can try all combos
  offline regardless of hash.
- Operational complexity: hashing libraries, migration, and slower tests for
  negligible gain.
- Users expect instant switching like Netflix profiles, friction should be minimal.

## Decision

Store PINs in **plain text** in the `accounts.pin` column.

Implement compensating controls:

- **Rate limiting:** `slowapi` limits `POST /api/auth/login` and
  `POST /api/auth/accounts` to `5/minute` per IP.
- **Secure cookies:** session cookie is `httponly`, `samesite=lax`, `secure` in
  production (`not DEBUG`), 30-day TTL, signed with PyJWT HS256 (ISS=MELEReview AUD=account exp 30d, iss/aud/jti) using `SECRET_KEY >=32 chars`.
- **No password reuse risk:** PINs are not passwords; we document they must not be
  reused for high-value accounts and show a warning in the UI/docs.
- **Scope:** `MySQL` + `SQLite` tests use same field; no separate secret store.
- **Future path:** if deployment becomes multi-tenant internet-facing, revisit
  and migrate to `argon2`/`bcrypt` with a migration script.

## Consequences

### Positive

- Simple code, fast tests, no hashing dep in hot path.
- Netflix-like UX: fast login, no key-stretching latency.
- Easy to inspect/debug in local dev and family use.

### Negative

- DB leak exposes PINs directly. Mitigated by rate limits and low account value,
  but requires disclosure to users.

### Tradeoffs Considered

| Option | Pros | Cons |
|---|---|---|
| Plain PIN + rate limit (chosen) | Simple, fast, honest about 4-digit entropy | DB leak = PIN leak |
| bcrypt PIN | Feels more secure | Same offline brute-force; adds complexity, slower |
| No PIN (open profiles) | Simplest | No separation of solutions |

## Verification

- `api/services/account_service.py` stores `pin` without hashing.
- `api/routes/auth.py` verifies by direct comparison, rate-limited.
- Auth tests assert plain-pin flow and 429 on brute force.
- This ADR documents the rationale and mitigations.
