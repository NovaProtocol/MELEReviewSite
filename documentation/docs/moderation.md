# Moderation

Two mechanisms, deliberately separate.

**Hiding** is a decision about one question or one solution. A moderator sets `is_hidden`, the row
stays, and the administrator can put it back.

**A ban** is a decision about a person. It hides everything that person wrote without touching a
single content row, because visibility is derived from the author's status.

## Hiding content

Any account holding `MODERATE` can hide:

| Route | Effect |
|---|---|
| `POST /api/questions/{id}/hide` | `questions.is_hidden = 1`, records who and when |
| `POST /api/solutions/{id}/hide` | `solutions.is_hidden = 1`, records who and when |

Hidden content disappears from the topic page and from every list. The row keeps its author, its
timestamps, and the moderator who hid it, so the administrator can see what happened and undo it.

## Restoring content

`POST /api/admin/content/{kind}/{id}/restore` with `kind` of `question` or `solution` clears
`is_hidden`, `hidden_by_user_id` and `hidden_at`. Restored content reappears immediately.

`GET /api/admin/content` returns everything currently hidden, with the subject and topic for a
question and the question text for a solution, so the administrator restores from context rather
than from an id.

## What a member sees

`GET /api/topics/{id}/questions` applies one filter:

```python
if not include_hidden:
    stmt = stmt.where(Question.is_hidden.is_(False), User.status == "active")
```

`include_hidden` is true only for an account holding `VIEW_HIDDEN`. A question written by a banned
member does not appear anywhere on the site, and it was never hidden: the author's status is doing
the work.

The same rule runs over solution images, so a banned member's uploaded solutions stop appearing
even on a question somebody else wrote.

## Why the split matters

A moderator hiding a bad question is a small, reversible, content-level decision. Revoking an
account's access is an account-level decision with a cascade behind it. If both wrote `is_hidden`,
restoring a mistakenly hidden question would also have to work out whether the author is banned, and
a ban would have to write one row per item and could never be cleanly reversed.

Two conditions, one place, no cascade writes.

## The audit trail

| Question | Answer |
|---|---|
| Who wrote this? | `questions.author_user_id` |
| Who hid it? | `questions.hidden_by_user_id` |
| When? | `questions.hidden_at` |
| Who banned the author? | `users.status_root_user_id` on the banned row itself |
| Why was this account revoked? | `users.status_reason` and `status_root_user_id` |

Nothing is deleted from the interface. The only destroy path is the one-shot legacy reset on first
boot, and that is logged.

## Community moderation

Members can push a question out of view without any moderator: once its score reaches -1, a
downvoted question leaves everyone's default list and only comes back under "Show downvoted".

That is a score, not a flag. One member at -1 is enough to hide it in practice, and a member can undo
their own vote, so the state is never permanent. The eye button is unrelated: it hides a question
for the one member who pressed it, and never for anyone else.

Hiding *for everyone* remains a human decision by an account holding `MODERATE`.
