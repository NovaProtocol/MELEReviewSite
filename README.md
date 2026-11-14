# MELE Review

A board-exam reviewer for the Philippine mechanical engineering licensure exam, built around a
shared question bank and an invitation chain instead of open sign-ups.

**Stack:** Python 3.14, FastAPI, Granian, MySQL 8.4, Caddy, Jinja2, Tailwind
**Docs:** MkDocs site at `/documentation/`

## What it does

The site opens on a landing page that is also the sign-in form. Registering needs an invitation
code from an existing member, so every account except the system administrator descends from
someone. That relationship is recorded and it is what the ban cascade walks.

After signing in, the library lists three subjects and their topics, seeded into the database from
`mysql/seed/taxonomy.sql`. A topic holds its questions; each question keeps four or five choices,
the correct one, an optional explanation, and the worked solutions members upload as images.

The right-hand rail holds the study tools: the thermodynamic cycle solver and six calculators. Type
a word into the rail and it filters by name and keywords, so `convert` finds the unit converter and
`carnot` opens the cycle solver.

## What is in an account

| Field | Note |
|---|---|
| `uid` | 32 hex characters, generated at creation, immutable, shown as the public id |
| `username` | changeable, unique, 3 to 32 characters |
| `email` | changeable, unique, used to sign in |
| `password_hash` | scrypt with a per-user salt, parameters stored with the hash |
| `bio`, `avatar_path` | optional profile, avatar written to the upload volume |
| `permissions` | one integer holding eight bit flags |
| `status` | `active`, `banned` or `revoked`, with the reason and the account that caused it |
| `invited_by_user_id` | the chain |

Changing a username keeps the `uid`, so questions and solutions stay attributed.

## Permissions

One `BIGINT` column, one bit per grant. Adding a permission introduces a new constant and never
renumbers an existing bit, so old rows keep their meaning.

| Bit | Name | Grants |
|---|---|---|
| 0 | `POST_QUESTION` | create and edit own questions |
| 1 | `ANSWER_QUESTION` | upload a worked solution |
| 2 | `INVITE` | mint single-use invitation codes |
| 3 | `MODERATE` | hide questions and solutions from members |
| 4 | `VIEW_HIDDEN` | see hidden content and restore it |
| 5 | `MANAGE_TAXONOMY` | add subjects and topics |
| 6 | `MANAGE_USERS` | ban, revoke, edit grants |
| 7 | `MANAGE_INVITES` | revoke any unused code |

New accounts get the first three. The system administrator holds all eight and is the only account
that can open `/admin`.

## How a ban works

Banning an account walks `invited_by_user_id` downward with one recursive query and revokes every
account beneath it, then cancels every unused code in that subtree. The confirmation dialog states
how many accounts will be revoked and how much content will stop appearing before anything happens.

Revoked is not the same as banned. A banned member is told they were banned; a revoked member is
told whose action removed their access and that they need a new invitation. Either way the content
stays in the database. Visibility is decided by two conditions in one place, so a ban writes only
to `users` and `invites` and reversing it needs no data migration:

```
a question is public when  is_hidden = 0  and  its author's status = 'active'
```

`Revoke invitations` runs the same cascade from an account that keeps its own access, which is the
response to a compromised account that invited people it should not have.

## Quick Start

```bash
# env comes from compose interpolation; there is no .env file
export DEPLOYMENT_TYPE=debug
export MYSQL_PASS=$(python3 -c "import secrets; print(secrets.token_hex(16))")
export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export ADMIN_USER=admin
export ADMIN_PASS=password
docker compose up -d --build
```

The site is at `http://127.0.0.1:7060/`. On first boot the app drops the retired tables from the
previous build, creates the schema, seeds the subjects and topics, and reconciles the system
administrator from `ADMIN_USER` and `ADMIN_PASS`.

## Ports

| Service | URL |
|---|---|
| Caddy | `http://127.0.0.1:7060` |
| App | `melereview_main:7061` (internal) |
| Documentation | `http://127.0.0.1:7060/documentation/` |
| MySQL | `melereview_db:3306` (internal) |

## Environment

| Variable | Required | Description |
|---|---|---|
| `DEPLOYMENT_TYPE` | yes | `debug` (no caching, cookies not Secure) or `production` |
| `MYSQL_PASS` | yes | MySQL root password and the app's database password |
| `MYSQL_USER` | no | `root` |
| `MYSQL_DATABASE` | no | `MELEReview` |
| `SECRET_KEY` | yes | Signs session tokens, at least 32 characters |
| `ADMIN_USER` | yes | System administrator's username, claimed on first boot |
| `ADMIN_PASS` | yes | System administrator's password, re-applied on every boot |
| `UPLOAD_DIR` | no | `/app/uploads` |
| `MAX_UPLOAD_BYTES` | no | `8388608` |
| `MAX_OPEN_INVITES` | no | `5` unused codes per member |
| `COOKIE_SECURE` | no | Derived from `DEPLOYMENT_TYPE`; set `false` for production over plain HTTP |

`ADMIN_PASS` is the environment's on every start. A password changed in the interface reverts at the
next restart, deliberately: the compose variables are the source of truth for that one account.

## Auth

Sessions are HS256 JWTs in an `HttpOnly`, `SameSite=Lax` cookie, carrying the user id and nothing
else. Every request re-reads the row, so a ban takes effect on the next request rather than when the
token expires. Mutating requests carry a double-submit CSRF token, and sign-in and registration are
rate limited to five attempts per minute per address.

Pages and uploads are `private, no-store`. Static assets keep a day-long public lifespan. The site
sits behind GateKeeper like the rest of the fleet, which is configured there and not here.

## Structure

```
app/                the FastAPI app
  bootstrap.py      legacy reset, schema, seed, administrator
  models.py         SQLAlchemy 2.0 tables
  permissions.py    the bit flags
  security.py       scrypt, session tokens, CSRF, codes
  services/         users, invites, library
  routes/           pages, auth, invites, library, media, admin, tools
  thermo/           cycle solver over CoolProp
  templates/        Jinja2, extending the shared shell
  static/           compiled Tailwind, app CSS, page JS, calculators
mysql/seed/         taxonomy.sql, executed at startup
caddy/              the single Caddyfile
documentation/      MkDocs site served at /documentation/
```

## License

All rights reserved. See [LICENSE](LICENSE).
