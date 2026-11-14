# Accounts and Invitations

Every account below the system administrator exists because somebody already inside the site minted
a code and gave it away. That one rule is what makes the invitation chain auditable and what makes
the ban cascade possible.

## The account row

| Column | Meaning |
|---|---|
| `id` | internal primary key |
| `uid` | 32 hex characters from `uuid4`, generated once, never changes, shown as the public id |
| `username` | unique, 3 to 32 characters from letters, digits, underscore, dot and hyphen |
| `email` | unique, lowercased, accepted as a sign-in identifier |
| `password_hash` | `scrypt$n$r$p$salt$hash`, parameters stored so the cost can rise later |
| `bio` | up to 500 characters |
| `avatar_path` | relative path inside the upload volume |
| `permissions` | one integer, eight bits |
| `is_system_admin` | exactly one account carries this |
| `status` | `active`, `banned` or `revoked` |
| `status_reason` | `banned` or `revoked`, for the notice copy |
| `status_root_user_id` | the account whose action caused this status |
| `invited_by_user_id` | the chain |
| `date_last_login`, `date_created`, `date_modified` | timestamps |

A username change keeps the `uid`, and the `uid` is what a profile or a citation should quote.
Nothing references the username, so a rename does not orphan anything.

## Password storage

`app/security.py` derives the hash with `hashlib.scrypt` at `n=16384`, `r=8`, `p=1`, a 32-byte
derived key, and 16 random bytes of salt per account. The stored string carries its own parameters:

```
scrypt$16384$8$1$<base64 salt>$<base64 hash>
```

Verification re-derives with the parameters from the string, so raising the cost later only affects
new hashes and old accounts keep working. Comparison is `hmac.compare_digest`.

## Sessions

Sign-in mints an HS256 JWT (`iss=MELEReview`, `aud=account`, `jti`, `exp` 30 days) containing the
user id and nothing else, and sets it as `melereview_session`: `HttpOnly`, `SameSite=Lax`, `Secure`
unless the deployment is plain HTTP, path `/`.

Every request decodes the token and re-reads the row. A token that is valid but names a banned or
revoked account buys nothing, which is what makes the cascade immediate instead of waiting out the
cookie.

## Invitations

A code is 16 hex characters from `secrets.token_hex(8)`, unique, and single use.

| Field | Meaning |
|---|---|
| `code` | the string that is sent to the invitee |
| `created_by_user_id` | who minted it |
| `used_by_user_id`, `used_at` | who redeemed it, and when |
| `revoked_at`, `revoked_by_user_id` | cancellation |

A member may hold at most `MAX_OPEN_INVITES` unused codes (default 5). Registration checks that the
code exists, is unused, is unrevoked, and that the account that minted it is still `active`. A code
from a banned inviter is refused with a message saying so, rather than silently failing.

Members see their own codes on `/profile`. The administrator sees every code on `/admin`, with who
minted it and its state, and can cancel any unused one.

## The chain, and the two cascades

`invited_by_user_id` is a self-reference. Walking it downward is one recursive query, supported by
both MySQL 8.4 and SQLite:

```sql
WITH RECURSIVE chain (id) AS (
    SELECT :root_id
    UNION ALL
    SELECT u.id FROM users u JOIN chain c ON u.invited_by_user_id = c.id
)
SELECT id FROM chain WHERE id <> :root_id
```

**Ban** (`POST /api/admin/users/{id}/ban`)

1. The target becomes `status = banned`, `status_reason = banned`, and its own id goes into
   `status_root_user_id`.
2. Every descendant becomes `status = revoked`, `status_reason = revoked`, with the banned account's
   id in `status_root_user_id`.
3. Every unused code owned by anyone in the subtree is stamped `revoked_at`.
4. One transaction.

**Revoke invitations** (`POST /api/admin/users/{id}/revoke-subtree`)

The same walk from an account that keeps its own access. Descendants are revoked, the target's own
unused codes are cancelled, and the target stays `active`. This is the response to a compromised
account that has already invited people it should not have.

Neither operation writes to `questions` or `solutions`. Hiding is derived from the author's status,
so the cascade touches two tables and reversing a single account needs no content migration.

## Before either operation

`GET /api/admin/users/{id}/ban-preview` returns what will happen:

```json
{
  "user": {"id": 12, "username": "someone", "uid": "..."},
  "direct_invitees": 3,
  "total_descendants": 11,
  "questions": 42,
  "solutions": 17,
  "open_invites": 4
}
```

The confirmation dialog shows those numbers and requires typing the username before the button
enables.

## What the affected member sees

`/status` is the only page an inactive account can load. Every other page redirects there.

**Banned**

> **@someone was banned by the system administrator.**
> Your account and everything you posted are hidden from the review group. The questions and
> solutions themselves stay on record.

**Revoked, because the root was banned**

> **@root was banned.**
> Your access was revoked because you were invited through @root, and an account below a banned one
> cannot keep access.

**Revoked, because the root had its invitations revoked**

> **@root revoked the invitations under them.**
> Your access was revoked as part of that, because you were invited through @root.

All three end with the same line:

> If you need access, you need to enter a new invitation from another person.

Signing out is the only other control on the page.

## Reactivating

`POST /api/admin/users/{id}/reactivate` restores one account to `active`. Descendants stay revoked:
a whole subtree is not silently resurrected, because the point of the cascade is that it has to be
rebuilt deliberately, one invitation at a time.
