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

## The filter menu

The controls live behind one **Filters** button, which carries the number of filters in use. Each is
independent of the others, because a question can be starred, hidden, unanswered and one you wrote
all at once; any combination is a valid request and they add up rather than replace each other.

| Control | Default | Effect |
|---|---|---|
| Answers | Show all | Answered only, Unanswered only, or everything |
| Favourites only | off | narrows to questions you starred |
| Include hidden | off | includes questions you hid yourself |
| Include downvoted | off | includes questions whose score is below zero |
| With a solution | off | only questions somebody has posted working on |
| Written by me | off | only the questions you wrote |

The server applies them (`answer_state`, `favourites`, `show_hidden`, `show_downvoted`,
`has_solution`, `mine`), so the menu only decides what to ask for and the list is never filtered in
the browser.

A list card is read-only and shows **only** the statement and its choices: no choice is marked, the
previous attempt is not replayed, and there is no feedback line. What you have answered is shown by
a green **ANSWERED** badge in the header instead. Answering belongs on the question's own page.

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

`POST /api/questions/{id}/attempt` with `{"chosen": "B"}`. One row per member per question, however
many tries:

| Column | Meaning |
|---|---|
| `chosen` | their most recent selection |
| `first_selection` | the first thing they picked, written once |
| `first_correct` | whether that first pick was right |
| `is_correct` | whether they have found the right answer at all |
| `attempts` | how many times they pressed a choice |

Rules:

- **A wrong answer reveals nothing.** The response carries `correct_choice: null` while they are
  wrong, so a second try is a real try. The right letter is only returned once they pick it.
- **A right answer locks the sheet.** Further selections return `409` rather than being counted, so
  `attempts` measures tries, not taps.
- **Answering is on the question's page only.** Choices in a list are rendered read-only.
- **Confirm before submitting.** The page asks "Final answer?" before it posts, because a wrong pick
  costs a try.

## Solutions are earned

Nothing about another member's solution reaches a viewer until they have answered the question
correctly:

| State | What the API returns |
|---|---|
| Not answered | `solutions: []`, `may_see_solutions: false` |
| Answered wrong | `solutions: []`, `may_see_solutions: false` |
| Answered right | the grid, `may_see_solutions: true` |

`solution_count` stays visible in every state, because it labels the link on the list card. The
bodies are what is withheld. A moderator or the administrator holding `VIEW_HIDDEN` keeps their
view, which is what makes moderation possible.

**Uploading is never gated.** A member can post their own working without unlocking anyone else's.

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

## Writing a question

The statement and the note are Markdown. The form shows a toolbar and two modes over one value:

- **Markdown** is a plain textarea holding the source, which is what the database stores.
- **Rich text** is the same source rendered by the server, inside a `contenteditable`. Switching to
  it posts the source to `/api/editor/preview`, so there is one parser and the editor cannot show
  something the reader will not get. Switching back serialises the DOM into Markdown in the browser.
- Submitting from either mode writes Markdown, because the rich view is flushed to its source first.

`app/markdown.py` is the only renderer. It escapes the author's text before applying any markup, so
the only tags in the output are the ones it writes. It covers headings, bold, italic, strikethrough,
superscript, inline code, fenced code, quotes, spoilers (`>!like this!<`), links, images, bullet and
numbered lists, and pipe tables. A link must be `http`, `https` or a site-relative path; anything
else is dropped rather than rendered.

## Images

An uploaded image is a row in `media` and a file on the `uploads_data` volume:

```
media  id, uid, path, content_type, byte_size, width, height,
       uploaded_by_user_id, question_id, date_created
```

The prose refers to it by uid: `![](/media/<uid>)`. That is a path on this site, not a URL with a
hostname, so a question keeps working if the domain changes. Nothing rewrites stored prose.

`question_id` records which question currently uses an image, and it is derived from the prose on
every save: anything the body or note references is claimed, and anything they stopped referencing
is released. "Where is this image used" is therefore answerable from the database rather than from
the author's memory.

`width` and `height` are read from the file header (PNG, JPEG and WebP), without decoding the image.
Uploads are capped by `MAX_MEDIA_BYTES` (8 MB by default) and the type is decided from magic bytes.

## Reply threads

A solution is the top of a thread. A reply answers the solution, and a reply can answer a reply, to
any depth:

```
replies        id, solution_id, parent_id, author_user_id, body, date_created
solution_votes id, solution_id, user_id, vote, date_created   UNIQUE (solution_id, user_id)
reply_votes    id, reply_id, user_id, vote, date_created      UNIQUE (reply_id, user_id)
```

`solution_id` is the thread root and never changes, so a whole thread loads with one query instead
of a walk. `parent_id` is the comment being answered, and is null for a first-level reply.

Any member who has earned the solutions may reply. A reply is text, up to 4000 characters; a
solution keeps its image and its caption. A reply's author may delete it, and so may the system
administrator. A banned author's replies leave the thread without being deleted, the same rule that
takes their questions out of the library. A reply whose parent left that way is lifted to the top of
the thread rather than vanishing with it.

### Sorting, once

The section carries one sort control: **Default**, **Top**, **Newest**. The choice is stored in the
browser, so it is set once and every solution and every reply in the section is read that way. There
is no per-thread or per-comment control.

- **Newest** is the timestamp alone.
- **Top** is the summed votes, newest first on a tie.
- **Default** is Reddit's hot order: `log10(max(votes, 1)) + age_seconds / 45000`. A reply with no
  votes is ranked purely by age, so something just posted sits at the top; roughly twelve hours of
  age costs one order of magnitude of votes, which is how an older reply with real support climbs
  back over a fresh one.

Sorting happens in the browser from `score` and `date_created`, both of which the payload carries.

### Score never hides a thread

The score threshold that quietly removes a badly received *question* from a list does not apply
here. A solution or a reply at any score is still shown; only the sort order moves it down. Downvotes
on questions are a spam control, and applying that to replies would let one person bury an answer.

### Validation

`app/media.py` decides the type from magic bytes, not from the client's content type:

| Signature | Accepted as |
|---|---|
| `\x89PNG\r\n\x1a\n` | PNG |
| `\xff\xd8\xff` | JPEG |
| `RIFF....WEBP` | WebP |

Anything else is `422`, and an upload beyond `MAX_UPLOAD_BYTES` is `413`. Files are written to a
`.part` name and renamed into place.

### Editing clears attempts

Changing a question's statement, choices or answer makes every attempt on it a measurement of a
different problem, so the attempt rows for that question are deleted outright and every affected
member's counters are recomputed. The author keeps their "questions added" count: they did write it,
and the row still exists.

**Hiding does not clear attempts.** A hidden question is the same question, and restoring it brings
back answers people had already given.

### Serving

`GET /media/{path}` requires a session: a solution is only meant for members inside the invitation
tree, so it is not on the public static mount. The route refuses anything outside the upload root,
and answers `Cache-Control: private, no-store`.
