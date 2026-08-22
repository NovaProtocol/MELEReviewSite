# MELE Review Documentation

MkDocs site for MELE Review — board-exam reviewer for Philippine Mechanical Engineering licensure exams.

Built with [MkDocs](https://www.mkdocs.org/) and the Material theme per the house `documentation/` pattern.

## Contents

| Section | Description |
|---------|-------------|
| [Home](./docs/index.md) | Overview and service map |
| [Getting Started](./docs/getting-started.md) | Prerequisites and startup |
| [Architecture](./docs/architecture.md) | System diagrams, networks, auth |
| [Questions](./docs/questions/index.md) | Question model, CRUD, search, tags |
| [Blocks](./docs/blocks/index.md) | Solution block editor (typed JSONB) |
| [Solver](./docs/solver/index.md) | Thermodynamic cycle solver + calculators |
| [API Reference](./docs/api/index.md) | REST + gRPC contract |

## Building Locally

```bash
pip install -r requirements.txt
mkdocs build
mkdocs serve    # preview at http://localhost:8000
```
