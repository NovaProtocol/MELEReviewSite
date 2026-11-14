# MELE Review Documentation

MkDocs site for MELE Review, the board-exam reviewer for the Philippine mechanical engineering
licensure exam.

## Contents

| Section | Description |
|---|---|
| [Home](./docs/index.md) | What the site is and how the pages read |
| [Getting Started](./docs/getting-started.md) | Running the stack, the first boot, inviting someone |
| [Architecture](./docs/architecture.md) | One app, one proxy, one database |
| [Accounts and Invitations](./docs/accounts-and-invitations.md) | The chain, both cascades, the notice copy |
| [Permissions](./docs/permissions.md) | The eight bits and where each is enforced |
| [Moderation](./docs/moderation.md) | Hiding, restoring, banning, revoking |
| [Questions and Solutions](./docs/questions.md) | The content model and the upload path |
| [Study Tools](./docs/tools.md) | The rail, the catalogue, the cycle solver |
| [Caching](./docs/caching.md) | What may be stored and for how long |
| [API Reference](./docs/api/index.md) | The JSON surface |
| [Docker Infrastructure](./docs/docker/index.md) | The stack in detail |

## Building locally

```bash
pip install -r requirements.txt
mkdocs build
mkdocs serve    # preview at http://localhost:8000
```

The container builds the site during `docker build` and serves it from `melereview_documentation` on
8005; Caddy exposes it at `/documentation/`.
