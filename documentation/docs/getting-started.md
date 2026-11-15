# Getting Started

## Run it

The stack reads its configuration from compose interpolation. There is no `.env` file.

```bash
export DEPLOYMENT_TYPE=debug
export MYSQL_PASS=$(python3 -c "import secrets; print(secrets.token_hex(16))")
export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export ADMIN_USER=admin
export ADMIN_PASS=password
docker compose up -d --build
```

Open `http://127.0.0.1:7060/`. That is the sign-in page, with the subject overview beside it.

## First boot

The app does four things at startup, in this order:

1. **Drops retired tables.** If the `users` table does not exist and any of `accounts`,
   `questions`, `solutions`, `tags`, `question_tags` or `question_flags` do, they are dropped with
   foreign key checks off. This runs once and logs the names. It is the reset from the previous
   build of this site.
2. **Creates and adapts the schema.** Missing tables are created; a missing column on an existing
   table is added. MySQL runs with `FOREIGN_KEY_CHECKS=0` for that batch.
3. **Seeds the taxonomy.** `mysql/seed/taxonomy.sql` runs statement by statement. Every statement
   is guarded with `NOT EXISTS`, so it never duplicates and it never overwrites a rename you made.
4. **Reconciles the system administrator.** If no administrator exists, `ADMIN_USER` is claimed or
   created. Every boot sets the account's permissions to all eight bits and, if `ADMIN_PASS` no
   longer verifies, replaces the hash.

Read `docker logs melereview_main` if something does not appear: each step logs what it did.

## Sign in and invite someone

Sign in with `ADMIN_USER` / `ADMIN_PASS`. You land on the library with three subjects and their 58
topics.

Go to **Profile**. Your invitations are there: press *Create an invitation* and send the 16-character
code to whoever you want to add. They open `/register`, paste the code, pick a username, email and
password, and they are in. Their account records you as the inviter, which is what the ban chain
follows later.

## Environment

| Variable | Required | Default | Description |
|---|---|---|---|
| `DEPLOYMENT_TYPE` | yes | n/a | `debug` or `production` |
| `MYSQL_PASS` | yes | n/a | MySQL root password and the app's database password |
| `SECRET_KEY` | yes | n/a | Session signing key, at least 32 characters |
| `ADMIN_USER` | yes | n/a | System administrator username |
| `ADMIN_PASS` | yes | n/a | System administrator password |
| `MYSQL_HOST` | no | `mysql-db` | Compose service DNS |
| `MYSQL_PORT` | no | `3306` | |
| `MYSQL_USER` | no | `root` | |
| `MYSQL_DATABASE` | no | `MELEReview` | |
| `DATABASE_URL` | no | built from `MYSQL_*` | Full SQLAlchemy URL, useful for tests |
| `UPLOAD_DIR` | no | `/app/uploads` | Where images are written |
| `MAX_UPLOAD_BYTES` | no | `8388608` | Largest accepted solution or avatar image |
| `MAX_MEDIA_BYTES` | no | `8388608` | Largest image accepted from the question editor |
| `MAX_OPEN_INVITES` | no | `5` | Unused codes per member |
| `COOKIE_SECURE` | no | from `DEPLOYMENT_TYPE` | Set `false` for production over plain HTTP |

## Local development without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install "pytest" "httpx" "pytest-asyncio"

export DEPLOYMENT_TYPE=debug MYSQL_PASS=devpass \
       SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
       ADMIN_USER=admin ADMIN_PASS=password
export DATABASE_URL=sqlite+aiosqlite:////tmp/dev.db

uvicorn --factory app:create_app --port 7061 --reload
```

SQLite is enough for development: the schema pass and the seed both work there. Uploads land in
`$UPLOAD_DIR`.

## Tests

```bash
pytest -q
```

The suite runs against SQLite with a temporary upload directory. It covers password hashing, the
session and CSRF rules, the invite chain and both cascades, permissions, moderation, uploads, the
page routes, the seeded taxonomy, the cache policy, the tool catalogue and the thermo solver.

## Preview the documentation

```bash
cd documentation
pip install -r requirements.txt
mkdocs serve
```

## Troubleshooting

**Sign-in appears to work but the session is gone on the next request.** The cookie is `Secure` and
you are on plain HTTP. Set `COOKIE_SECURE=false`.

**The library is empty.** The seed did not run. Check the startup log for
`taxonomy seed missing at` — the container needs `mysql/seed/taxonomy.sql` in the image, and the
Dockerfile copies `mysql/`.

**The administrator password keeps reverting.** That is intended: `ADMIN_PASS` wins on every boot.

**A registration is refused with "the person who issued that code no longer has access".** The
inviter was banned or revoked between minting the code and it being used. Mint a new one from an
active account.
