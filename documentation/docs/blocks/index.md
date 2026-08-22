# Solution Blocks

Rich per-question solutions (v2): typed block arrays stored as `Text` JSON (MySQL `TEXT`, Python `default="[]"` — no `server_default` per MySQL 8.4 rule). One `Solution` row per `(question_id, account_id)`.

## Model (`solutions`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK |  |
| `question_id` | FK `questions.id` CASCADE, indexed |  |
| `account_id` | FK `accounts.id` CASCADE, indexed | Net per-user solution |
| `convention` | `String(20)` | `metric` \| `english` \| `custom` \| `imperial`, `server_default 'metric'` |
| `blocks` | `Text` | JSON array of `Block` union; `nullable=False, default="[]"` |
| `date_created/modified` | DateTime | `server_default func.now()` |

## Block Union (Pydantic)

```python
class ConstantItem(BaseModel):
    name: str
    value: str
    unit: str = ""
    is_private: bool = False


class ConstantBlock(BaseModel):
    type: Literal["constants"]
    id: int | None = None
    constants: list[ConstantItem]


class FormulaBlock(BaseModel):
    type: Literal["formula"]
    id: int | None = None
    latex: str
    result: str | None = None


class AnswerBlock(BaseModel):
    type: Literal["answer"]
    id: int | None = None
    variable: str
    unit: str = ""
    result: str | None = None


class LegacyAnswerBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answer: int


Block = ConstantBlock | FormulaBlock | AnswerBlock | LegacyAnswerBlock
```

Backend validates every `PUT` via the `Block` union; unknown `type` is rejected with `400/422`. Stored verbatim as `json.dumps(blocks)` in `solutions.blocks`.

## REST Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/questions/{id}/solution` | optional (cookie) — returns caller's own or 401 if anon and question needs it? Actually `get_solution` returns own row; if none, 404 | Fetch own solution blocks + convention |
| `PUT` | `/api/questions/{id}/solution` | `get_current_account` | Upsert; validates blocks via Pydantic, writes `blocks` JSON |
| `GET` | `/api/my/solutions` | `get_current_account` | All caller's solutions across questions (used by `questions.js` + profile stats) |
| `GET` | `/api/questions/{id}/solutions` | — | All solutions for a question with `account_name` (admin/debug) |

Counts: every list endpoint returns `X-Total-Count`.

Example `PUT`:

```bash
curl -X PUT http://127.0.0.1:7060/api/questions/42/solution \
  -H "Content-Type: application/json" -H "Cookie: session=..." \
  -d '{
    "convention": "metric",
    "blocks": "[{\"type\":\"constants\",\"constants\":[{\"name\":\"P1\",\"value\":\"101.325\",\"unit\":\"kPa\"}]},{\"type\":\"formula\",\"latex\":\"P_2 = P_1 \\\\cdot r_p\",\"result\":\"203 kPa\"},{\"type\":\"answer\",\"variable\":\"W_net\",\"unit\":\"kJ/kg\",\"result\":\"42.1\"}]"
  }'
```

Note: `blocks` is a JSON *string* (the column stores text) — the HTTP `SolutionWrite.blocks` field accepts a string; the frontend's `createBlocksEditor` produces the array and stringifies it before `PUT`.

## gRPC

`SolutionService` (proto `api.v1`):

- `GetSolution(GetSolutionRequest) -> Solution` (`question_id` + caller `account_id`; NOT_FOUND when no row)
- `PutSolution(PutSolutionRequest) -> Solution` (validates `Block` union server-side)
- `ListMySolutions(ListMySolutionsRequest) -> ListMySolutionsResponse`

Shares `solution_service.py` with the HTTP routes. gRPC errors use `context.set_code(StatusCode.NOT_FOUND / INVALID_ARGUMENT)` and map to `404/400` at the HTTP edge.

## Frontend

- `web/static/js/solution_blocks.js` — `createBlocksEditor(container, initialBlocks)` renders editable typed blocks (constants/formulas/answers), MathQuill + KaTeX + math.js for `formula` latex evaluation.
- `web/static/js/questions.js` — per-question expand to show solution blocks, `GET /api/questions/{id}/solution`, inline edit when owned.
- `web/static/js/profile.js` — aggregates `GET /api/my/solutions` to show answer counts.

Adaptive migration note: `solutions.blocks` is `Text` with no `server_default`; creation via `default="[]"` keeps MySQL 8.4 happy.
