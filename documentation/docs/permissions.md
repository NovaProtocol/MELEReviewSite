# Permissions

One `BIGINT` column on `users`, one bit per grant, in `app/permissions.py`. A new permission
introduces a new constant and never renumbers an existing bit, so stored masks keep their meaning.

| Bit | Value | Constant | Grants |
|---|---|---|---|
| 0 | 1 | `POST_QUESTION` | create a question, edit your own |
| 1 | 2 | `ANSWER_QUESTION` | upload a worked solution |
| 2 | 4 | `INVITE` | mint invitation codes |
| 3 | 8 | `MODERATE` | hide any question or solution |
| 4 | 16 | `VIEW_HIDDEN` | see hidden content and restore it |
| 5 | 32 | `MANAGE_TAXONOMY` | add and rename subjects and topics |
| 6 | 64 | `MANAGE_USERS` | ban, revoke, reactivate, edit grants |
| 7 | 128 | `MANAGE_INVITES` | revoke any unused code |

`ALL` is `255`. `DEFAULT` is `POST_QUESTION | ANSWER_QUESTION | INVITE` (`7`), which is what a newly
registered member receives.

## Using a bit

```python
from app import permissions

permissions.has(user.permissions, permissions.MODERATE)
permissions.require(user.permissions, permissions.POST_QUESTION)  # raises 403
permissions.describe(user.permissions)                            # ["Moderate content"]
```

A route that needs a bit takes the dependency form:

```python
@router.post("/questions")
async def create_question(user: User = Depends(require_permission(permissions.POST_QUESTION))):
    ...
```

`/admin` and everything under `/api/admin` require `is_system_admin`, not a bit. The flag is
separate on purpose: a permission mask is something the owner edits, and the administrator is
something the environment creates.

## Where each bit is checked

| Bit | Enforced in |
|---|---|
| `POST_QUESTION` | `services/library.create_question`, plus the `/questions/new` page |
| `ANSWER_QUESTION` | `routes/library.upload_solution` |
| `INVITE` | `services/invites.create_invite`, plus the profile page's invitation panel |
| `MODERATE` | `services/library.hide_question`, `routes/library.hide_solution`, and the edit path for someone else's question |
| `VIEW_HIDDEN` | `routes/library` list and detail, which include hidden rows for a holder |
| `MANAGE_TAXONOMY` | the three taxonomy routes under `/api/admin` |
| `MANAGE_USERS` | documented grant, exercised through the administrator page |
| `MANAGE_INVITES` | documented grant, exercised through the administrator page |

The last two are carried by the flag as well, so an administrator who grants them to a moderator
does not create a second route into `/admin`. The grid in the interface shows every bit and is the
record of who holds what.

## Why bits and not columns

Eight booleans would be eight columns, eight edits to the grid, and eight ways for a query to
disagree with the screen. One integer is one read, one comparison, and one write:

```python
user.permissions |= permissions.MODERATE      # grant
user.permissions &= ~permissions.MODERATE     # revoke
```

The trade is that a mask is opaque in a raw SQL shell. `GET /api/admin/users` returns both the
integer and `permission_labels`, so the numbers are readable without decoding by hand.

## Editing grants

`PUT /api/admin/users/{id}/permissions` takes `{"permissions": <int>}`, clamps it to `ALL`, and
returns the updated row. The administrator page renders one toggle per bit and sends the recomputed
mask on each change.

The system administrator's own mask cannot be edited from the interface: it is reset to `ALL` on
every boot from `ADMIN_USER` / `ADMIN_PASS`, so an edit there would not survive a restart and would
be misleading.
