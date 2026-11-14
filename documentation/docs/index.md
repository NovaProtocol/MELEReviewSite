# MELE Review

Board-exam reviewer for the Philippine mechanical engineering licensure exam. A shared question
bank organised by subject and topic, a worked-solution image per question per member, and a set of
study tools in a side rail.

**Stack:** Python 3.14, FastAPI, Granian, MySQL 8.4, Caddy, Jinja2, Tailwind. Auth is scrypt
passwords over PyJWT HS256 sessions. Schema work happens at startup rather than through a
migration tool.

## Services

| Service | Container | Port | Route |
|---|---|---|---|
| Caddy | `melereview_caddy` | 7060, loopback | everything |
| App | `melereview_main` | 7061, internal | `/`, `/api/*`, `/media/*`, `/tools/*` |
| Documentation | `melereview_documentation` | 8005, internal | `/documentation/*` |
| MySQL 8.4 | `melereview_db` | 3306, internal | n/a |

Two named volumes: `mysql_data` and `uploads_data` (mounted at `/app/uploads`).

## What it does

- **Accounts** invited by code, with an immutable `uid` and a changeable username.
- **An invite chain** that a ban walks recursively, revoking everyone beneath the banned account.
- **Hidden, not deleted**: a moderator hides, the administrator restores, and a ban hides a whole
  history by changing nothing but the author's status.
- **Subjects and topics** seeded from SQL into the database, editable by an administrator.
- **Questions** with four or five choices, the correct letter, an optional explanation, and a
  bookmark per member.
- **Solutions as images** uploaded by members and streamed back through an authenticated route.
- **Seven study tools** in a searchable rail, including the CoolProp cycle solver.

## Reading order

1. [Getting Started](getting-started.md) — run it, sign in, invite someone.
2. [Architecture](architecture.md) — one app, one proxy, one database.
3. [Accounts and Invitations](accounts-and-invitations.md) — the chain, the cascade, the copy.
4. [Permissions](permissions.md) — the bits and what each one grants.
5. [Moderation](moderation.md) — hide, restore, ban, revoke.
6. [Questions and Solutions](questions.md) — the content model and the upload path.
7. [Study Tools](tools.md) — the rail and the solver.
8. [Caching](caching.md) — what may be stored and for how long.
9. [API](api/index.md) — the JSON surface.
10. [Docker Infrastructure](docker/index.md) — the stack in detail.
