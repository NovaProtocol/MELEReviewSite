# Questions

Multiple-choice questions with tags, search, filtering, pagination, and moderation. Single source of truth in `api/models.py` (`questions`, `tags`, `question_tags`, `question_flags`, `accounts`).

## Model

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Autoincrement |
| `question_text` | Text | Required |
| `choice_a` … `choice_e` | Text | `e` nullable; rendered as A–E |
| `answer` | Integer | 0-indexed choice index; nullable |
| `solution` | Text | Legacy free-text solution (kept alongside blocks) |
| `flagged` | Boolean | `true` when >=1 flag exists |
| `active` | Boolean | `server_default 1`; hidden questions filtered by default |
| `account_id` | FK `accounts.id` SET NULL | Author; used for ownership |
| `date_created/modified` | DateTime | `server_default func.now()` |
| Tags | M2M `question_tags` | Unique tag names, bulk-fetched via `tags_for_questions` |

Ownership rule (`check_ownership`): unowned questions are admin-only; otherwise author must match.

## REST Endpoints (via Caddy `handle /api/*` → `melereview_api:8082`)

All list endpoints return `X-Total-Count` and expose `X-Request-ID`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/questions?search=&tag=&include_inactive=&page=&per_page=&envelope=` | none | List (default `active` only). `envelope=true` → `{items,total,page,per_page}` else array. |
| `GET` | `/api/questions/{id}` | none | Single question + tags + author name |
| `POST` | `/api/questions` | `get_current_account` (cookie) | Create; body `QuestionWrite` + `tags[]`; sets `account_id` |
| `PUT` | `/api/questions/{id}` | owner/admin | Update; ownership checked |
| `DELETE` | `/api/questions/{id}` | owner/admin | Cascade deletes `solutions` via FK |
| `POST` | `/api/questions/{id}/flag` | `get_current_account` | Toggle flag; `flag_count >= ceil(10% of active accounts)` auto-deactivates (`active=false`) |
| `GET` | `/api/tags` | none | All tags ordered by name |

```python
# QuestionWrite
class QuestionWrite(BaseModel):
 question_text: str
 choice_a: str
 choice_b: str
 choice_c: str
 choice_d: str
 choice_e: str | None = None
 answer: int | None = None
 solution: str | None = None
 active: bool = True
 tags: list[str] = []
```
Pagination helper: `GET /api/questions?page=1&per_page=100`, response header `X-Total-Count: 123`, `Access-Control-Expose-Headers: X-Total-Count, X-Request-ID`.

## gRPC Surface (internal, `melereview_api:50051`)

Proto package `api.v1`, service `QuestionService` (see [API Reference](../api/index.md)):

- `ListQuestions(ListQuestionsRequest) -> ListQuestionsResponse`
- `GetQuestion(GetQuestionRequest) -> Question`
- `CreateQuestion(CreateQuestionRequest) -> Question`
- `UpdateQuestion(UpdateQuestionRequest) -> Question`
- `DeleteQuestion(DeleteQuestionRequest) -> Empty`

Web server-side call example:

```python
from web.grpc_client import get_question_via_grpc

q = await get_question_via_grpc(question_id=42)
```

Browser traffic stays on HTTP via Caddy; `web` dials `grpc.aio.insecure_channel("melereview_api:50051")` only when it needs server-side enrichment (e.g., SSR preload). Servicer delegates to the same `question_service.py` functions as the HTTP routes, no duplicated logic.

## Frontend

`web/templates/questions.html` + `web/static/js/questions.js`, search input, tag select, inactive toggle, per-question answer buttons, flagging, inline solution-block editor. `web/templates/question_form.html`, create/edit with tag chips and choice fields.
