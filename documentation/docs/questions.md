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
| `explanation` | optional, shown behind a disclosure on the card |
| `is_hidden` | moderator visibility |
| `hidden_by_user_id`, `hidden_at` | who hid it and when |

`POST /api/questions` requires `POST_QUESTION`. `PUT /api/questions/{id}` allows the author, or any
account holding `MODERATE`.

## Attempts

`POST /api/questions/{id}/attempt` with `{"chosen": "B"}` records one attempt per member per
question, storing the chosen letter and whether it was right. A second attempt overwrites the first:
the row is the member's standing answer, not a log.

The response carries `is_correct` and `correct_choice`, so the page can mark the correct choice and
the member's wrong pick at the same time. The question card reveals the answer on the first attempt
rather than only after a click, which is what the previous build did too.

`GET /api/me/progress` returns answered, correct, accuracy and bookmark count for the profile header
and the library stats.

## Solutions are images

A worked solution is a photograph or a screenshot of the work, not structured text. Each member has
at most one solution per question: uploading again replaces the image and deletes the old file.

### Why the bytes are not in MySQL

An 8 MB phone photo is larger than MySQL's default `max_allowed_packet`, would be buffered in memory
on every read, and would inflate every database backup and dump with data that never needs to be
queried.

So the database stores a reference and the file lives on disk:

```
solutions  id, question_id, author_user_id, image_path, note, is_hidden,
           hidden_by_user_id, hidden_at, date_created
           UNIQUE (question_id, author_user_id)
```

`image_path` is relative (`solutions/<uuid>.png`), written under `UPLOAD_DIR` in a container on the
`uploads_data` volume. Avatars use the same store and the same route, so there is one serving path
instead of two.

A future tool that cleans or re-encodes the images rewrites files in that directory and needs no
schema change, which was the reason the requirement mentioned storing raw images for now.

### Validation

`app/media.py` decides the type from magic bytes, not from the client's content type:

| Signature | Accepted as |
|---|---|
| `\x89PNG\r\n\x1a\n` | PNG |
| `\xff\xd8\xff` | JPEG |
| `RIFF....WEBP` | WebP |

Anything else is refused with `422`. An upload larger than `MAX_UPLOAD_BYTES` is refused with `413`.
Files are written to a `.part` name and renamed into place, so a half-written file never appears.

### Serving

`GET /media/{path}` requires a session. That is the point: a solution is only meant for members
inside the invitation tree, so it is not behind the static mount, which is public. The route
resolves the path and refuses anything outside the upload root, so a traversal attempt is a `404`
rather than a file read.

Responses carry `Cache-Control: private, no-store`.

### What members see

The topic page lists each question with its choices, a bookmark toggle, an optional explanation, and
a grid of every visible solution image with the author's username. Clicking an image opens it full
size. A member with `ANSWER_QUESTION` gets a file picker and an upload button on each question.

Solutions from hidden members are filtered out by the author-status rule, so a ban reaches the images
as well as the questions.

## Bookmarks

`POST /api/questions/{id}/bookmark` toggles a personal marker. `GET /api/topics/{id}/questions?bookmarked=true`
filters the topic to bookmarked questions. A bookmark has no effect on anyone else's view.
