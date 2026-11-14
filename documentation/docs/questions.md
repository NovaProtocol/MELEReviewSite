# Questions and Solutions

## Subjects and topics

The taxonomy is data, not code. Three subjects hold 58 topics, seeded from
`mysql/seed/taxonomy.sql` on every boot. An administrator can add, rename and deactivate from
`/admin`; a normal member cannot change the taxonomy at all.

```
subjects  id, name, display_order
topics    id, subject_id, name, display_order, is_active
```

`GET /api/subjects` returns the tree with a question count per topic, which is what the library page
renders and what the sign-in page summarises.

## A question

| Column | Meaning |
|---|---|
| `topic_id` | the topic it belongs to; only an active topic is accepted |
| `author_user_id` | who wrote it |
| `body` | the question text |
| `choice_a` to `choice_e` | four required choices, the fifth optional |
| `correct_choice` | one of `A` to `E` |
| `explanation` | optional, shown behind a disclosure |
| `is_hidden` | moderator visibility, for everyone |
| `hidden_by_user_id`, `hidden_at` | who hid it and when |

`POST /api/questions` requires `POST_QUESTION`. `PUT /api/questions/{id}` allows the author, or any
account holding `MODERATE`.

## The card

A question in a list reads as a post:

```
 vote    avatar  @name  11-14-2026                    star  eye
 rail    question text
  up     A  choice
         B  choice
  0      C  choice
         D  choice
  down   Open question
```

The header carries the author's avatar, `@username` and the date. The star and the eye are that
member's own state; the vote rail is the group's.

## Star, eye and votes

Three independent per-member values live in one `question_flags` row:

| Column | Meaning |
|---|---|
| `is_favourite` | starred for later |
| `is_hidden` | hidden from this member's list only |
| `vote` | `1`, `-1` or `0` |

**Favourite and hide are independent.** A question can be both: saved for later and out of the way.
Asking for `favourites=true` returns starred questions even if you hid them, because that is an
explicit request to see them.

The **score** in the rail is the sum of every member's vote, computed per list. Upvoting then
upvoting again clears the vote.

## The three filters

Above the list, each defaulting to the safe side:

| Control | Default | Effect |
|---|---|---|
| Favourites only | off | narrows to questions you starred |
| Show hidden | off | includes questions you hid yourself |
| Show downvoted | off | includes questions whose score is below zero |

**A downvoted question leaves the default list.** A question at -1 or lower is the group's own
moderation: it disappears for anyone who has not asked to see it. That is the spam control, and it is
why "Show downvoted" exists rather than a delete.

Moderator hiding is a different thing and stays separate. It is gated on `VIEW_HIDDEN` and is never
folded into the "Show hidden" toggle, so a moderator's own eye button keeps working instead of
appearing broken.

## The question page

`/topics/{topic_id}/{question_id}` is the full view: the same card, then the solutions.

Opening the page does **not** reveal the solutions. They sit behind one line of text:

> **Show other people's solutions**

Until it is clicked, no solution markup is in the document at all: the list endpoint returns
`solutions: []` for every card, and the detail page renders the grid only on the click. Uploading
your own solution is available without revealing anyone else's, so the page works as a place to
answer without being a place that spoils the answer.

| Element | Before the click | After |
|---|---|---|
| Solution images | not in the DOM | grid of images |
| Solution count on the list card | shown | shown |
| Upload control | available | available |
| "Show other people's solutions" | visible | replaced by the grid |

## Attempts

`POST /api/questions/{id}/attempt` with `{"chosen": "B"}` records one attempt per member per
question, storing the chosen letter and whether it was right. A second attempt overwrites the first.

The response carries `is_correct` and `correct_choice`, so the card marks the correct choice and the
member's wrong pick at the same time.

## Solutions are images

A worked solution is a photograph or a screenshot of the work. Each member has at most one solution
per question: uploading again replaces the image and deletes the old file.

### Why the bytes are not in MySQL

An 8 MB phone photo is larger than MySQL's default `max_allowed_packet`, would be buffered in memory
on every read, and would inflate every database backup with data that never needs to be queried.

```
solutions  id, question_id, author_user_id, image_path, note, is_hidden,
           hidden_by_user_id, hidden_at, date_created
           UNIQUE (question_id, author_user_id)
```

`image_path` is relative (`solutions/<uuid>.png`), written under `UPLOAD_DIR` on the `uploads_data`
volume. Avatars use the same store and the same route.

A future tool that cleans or re-encodes the images rewrites files in that directory and needs no
schema change.

### Validation

`app/media.py` decides the type from magic bytes, not from the client's content type:

| Signature | Accepted as |
|---|---|
| `\x89PNG\r\n\x1a\n` | PNG |
| `\xff\xd8\xff` | JPEG |
| `RIFF....WEBP` | WebP |

Anything else is `422`, and an upload beyond `MAX_UPLOAD_BYTES` is `413`. Files are written to a
`.part` name and renamed into place.

### Serving

`GET /media/{path}` requires a session: a solution is only meant for members inside the invitation
tree, so it is not on the public static mount. The route refuses anything outside the upload root,
and answers `Cache-Control: private, no-store`.
