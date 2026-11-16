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
- **Questions** as post cards: author, date, the statement and its choices, with a star, a personal
  hide and an up/down vote on each. A list shows the question, its choices and an ANSWERED badge;
  it never marks a choice or replays the previous answer.
- **One filter menu** on a topic, holding independent controls: answer state, favourites, hidden,
  downvoted, has a solution, written by me.
- **A Markdown editor** with a rich-text view of the same source, a formula palette that typesets
  LaTeX (KaTeX, vendored), and images uploaded to a directory and tracked in a `media` table.
- **No dead uploads**: an image removed by an edit is deleted, a cancelled edit hands its uploads
  back, and a startup sweep clears anything an abandoned form left behind.
- **No spoilers**: a question's page keeps other people's solutions behind one click, and the list
  never carries them at all.
- **Solutions as prose** written in the same editor as a question, with formulas and images,
  each with a reply thread that nests to any depth and is sorted once for the whole section.
- **Votes on solutions and replies**, summed per member, deciding the *Top* order; the *Default*
  order trades votes against age so a fresh reply outranks a stale one until an older one earns
  enough.
- **Study tools** in a searchable rail: a CoolProp cycle solver, steam tables with the state
  plotted on the dome, psychrometrics, pipe flow, heat transfer, strength and machine elements.

## Reading order

1. [Getting Started](getting-started.md) — run it, sign in, invite someone.
2. [Architecture](architecture.md) — one app, one proxy, one database.
3. [Accounts and Invitations](accounts-and-invitations.md) — the chain, the cascade, the copy.
4. [Permissions](permissions.md) — the bits and what each one grants.
5. [Moderation](moderation.md) — hide, restore, ban, revoke.
6. [Questions and Solutions](questions.md) — the content model, attempts and the upload path.
7. [Member Metrics](metrics.md) — the counters and the two rates.
8. [Search and Tags](search-and-tags.md) — finding a question, and tags that cross the tree.
9. [Study Tools](tools.md) — the rail and the solver.
10. [Caching](caching.md) — what may be stored and for how long.
11. [API](api/index.md) — the JSON surface.
12. [Docker Infrastructure](docker/index.md) — the stack in detail.
