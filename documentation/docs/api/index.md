# API Reference

Every route lives on the one app behind Caddy (`http://127.0.0.1:7060`). Responses carry
`X-Request-ID`; errors come back as `{"error": {"code", "message", "request_id"}}` with JSON asked
for, and as a styled page for a browser.

## Auth and CSRF

The session is a `melereview_session` cookie: HS256 JWT, `HttpOnly`, `SameSite=Lax`, 30 days.

Every mutating request (`POST`, `PUT`, `PATCH`, `DELETE`) must send the double-submit token:

```bash
curl -X POST http://127.0.0.1:7060/api/auth/login \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <value of the melereview_csrf cookie>" \
  -d '{"identifier": "admin", "password": "password"}'
```

The token is in the `melereview_csrf` cookie, which the page's own JavaScript reads reason the cookie
is not `HttpOnly`. A missing or mismatched pair is `403`.

## Auth

| Method | Path | Auth | Body |
|---|---|---|---|
| `POST` | `/api/auth/login` | none, 5/min | `{identifier, password}`; identifier is username, email or uid |
| `POST` | `/api/auth/logout` | none | clears the cookie |
| `POST` | `/api/auth/register` | none, 5/min | `{invite_code, username, email, password}` |
| `GET` | `/api/auth/me` | session | the viewer plus progress |
| `PUT` | `/api/auth/username` | session | `{username}` |
| `PUT` | `/api/auth/email` | session | `{email}` |
| `PUT` | `/api/auth/password` | session | `{current, new}` |
| `PUT` | `/api/auth/bio` | session | `{bio}` |
| `POST` | `/api/auth/avatar` | session | multipart `file` |

Login failures: `401` for a wrong password, `403` with the status name (`banned` / `revoked`) for an
inactive account, which is how the client knows to send the visitor to `/status`.

## Invitations

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/invites` | session | your own codes |
| `POST` | `/api/invites` | session + `INVITE` | `409` when the open-code cap is reached |

## Library

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/api/subjects` | session | subjects, topics, question counts |
| `GET` | `/api/topics/{id}/questions` | session | `?search=`, `?favourites=true`, `?show_hidden=true`, `?show_downvoted=true` |
| `GET` | `/api/questions/{id}` | session | `404` for hidden unless you hold `VIEW_HIDDEN` |
| `POST` | `/api/questions` | session + `POST_QUESTION` | |
| `PUT` | `/api/questions/{id}` | author, or `MODERATE` | |
| `POST` | `/api/questions/{id}/attempt` | session | `{chosen}`; `correct_choice` is null while wrong; `409` once solved |
| `GET` | `/api/questions/{id}` | session | the full question, including its solutions |
| `POST` | `/api/questions/{id}/favourite` | session | toggles the star, returns the new state |
| `POST` | `/api/questions/{id}/hide-for-me` | session | toggles this member's own hide |
| `POST` | `/api/questions/{id}/vote` | session | `{direction: 1 \| -1}`; the same vote twice clears it |
| `POST` | `/api/questions/{id}/solution` | session + `ANSWER_QUESTION` | multipart `file`, optional `note` |
| `DELETE` | `/api/questions/{id}/solution` | session, own | deletes the row and the file |
| `POST` | `/api/questions/{id}/hide` | session + `MODERATE` | |
| `POST` | `/api/solutions/{id}/hide` | session + `MODERATE` | |
| `GET` | `/api/me/progress` | session | questions, answered, solved, the two rates, capped average tries, favourites |

## Media

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/media/{path}` | session | PNG, JPEG or WebP from the upload volume; `private, no-store` |

Solutions are only returned once the viewer has answered the question correctly; see
[Questions and Solutions](../questions.md#solutions-are-earned).

## Administration

All of these require `is_system_admin`.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/admin/overview` | counts per status, content totals |
| `GET` | `/api/admin/users` | `?search=`, `?status=`, `?page=`, `?per_page=` |
| `GET` | `/api/admin/users/{id}/chain` | the inviter and everyone beneath |
| `PUT` | `/api/admin/users/{id}/permissions` | `{permissions}` clamped to `ALL` |
| `GET` | `/api/admin/users/{id}/ban-preview` | what a ban would revoke |
| `POST` | `/api/admin/users/{id}/ban` | bans the target, revokes descendants |
| `POST` | `/api/admin/users/{id}/revoke-subtree` | revokes descendants, keeps the target |
| `POST` | `/api/admin/users/{id}/reactivate` | restores one account |
| `GET` | `/api/admin/invites` | every code |
| `DELETE` | `/api/admin/invites/{id}` | cancels an unused code |
| `GET` | `/api/admin/content` | hidden questions and solutions |
| `POST` | `/api/admin/content/{kind}/{id}/restore` | `kind` is `question` or `solution` |

Taxonomy routes require `MANAGE_TAXONOMY` instead of the flag:

| Method | Path | Body |
|---|---|---|
| `POST` | `/api/admin/subjects` | `{name}` |
| `PUT` | `/api/admin/subjects/{id}` | `{name}` |
| `POST` | `/api/admin/topics` | `{subject_id, name}` |
| `PUT` | `/api/admin/topics/{id}` | `{is_active}` |

## Tools

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/api/tools/cycle` | session | cycle solver; `format` of `data` or `plot` |

## Health

| Method | Path | Auth |
|---|---|---|
| `GET` | `/health` | none, returns `{"status": "ok"}` |

`/health` is the only unauthenticated route on the app. It exists for the container healthcheck and
the Caddy probe.

## Examples

Sign in and list the subjects:

```bash
CSRF=$(curl -s -c jar http://127.0.0.1:7060/ -o /dev/null -D - | grep melereview_csrf | sed 's/.*=\([^;]*\).*/\1/')
curl -s -b jar -c jar -X POST http://127.0.0.1:7060/api/auth/login \
  -H "Content-Type: application/json" -H "X-CSRF-Token: $CSRF" \
  -d '{"identifier": "admin", "password": "password"}'
curl -s -b jar http://127.0.0.1:7060/api/subjects | head -c 400
```

Upload a solution:

```bash
curl -s -b jar -X POST http://127.0.0.1:7060/api/questions/1/solution \
  -H "X-CSRF-Token: $CSRF" -F "file=@worked.png" -F "note=Used the steam tables"
```

Preview a ban:

```bash
curl -s -b jar http://127.0.0.1:7060/api/admin/users/7/ban-preview
```
