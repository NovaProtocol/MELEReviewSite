# Member Metrics

Each member has five counters on their `users` row. They exist so a profile renders in one query
instead of an aggregate over every attempt.

| Column | Meaning |
|---|---|
| `metric_questions` | questions they wrote, hidden ones included |
| `metric_answered` | questions they have at least one attempt on |
| `metric_first_correct` | of those, how many were right on the first selection |
| `metric_solved` | of those, how many have been answered correctly at all |
| `metric_attempts` | sum of `min(attempts, 4)` over answered questions |

## The three rates

| Label | Formula | Reads as |
|---|---|---|
| First answer success rate | `metric_first_correct / metric_answered` | how often the first attempt is correct |
| Overall success rate | `metric_solved / metric_answered` | how often the question is eventually solved |
| Average attempts | `metric_attempts / metric_answered` | how much work each question takes |

**Average attempts is capped at 4 per question.** Pressing two choices alternately a hundred times
is one repeated failure, not a hundred attempts, so the cap keeps a single question from defining the
average. The figure therefore reads between 1.0 and 4.0.

The two rates differ in a way that matters: a member who is careful but slow has a low first-answer
rate and a high overall rate, while a member who guesses quickly and never retries has the opposite.
Both are shown, since neither is meaningful alone.

## How they are maintained

`app/services/metrics.py` owns them. **Nothing increments them.** Every change that could move a
number calls `refresh_user` or `refresh_many`, which recomputes from the attempt rows with one
aggregate. That is more work than a counter bump and it cannot drift — which matters because
editing a question deletes attempt rows in bulk, and a decrement would have to be exactly right about
how many.

Calls are placed at:

| Event | What runs |
|---|---|
| an attempt is recorded | `refresh_user` for that member |
| a question is created | `refresh_user` for the author |
| a question is edited | attempts cleared, then `refresh_many` for everyone affected |
| startup | `refresh_all_metrics`, so a column added by an adaptive migration is filled from the rows rather than reading as zero |

**A cast worth knowing about.** The aggregate sums booleans, and SQLite sums a boolean column to a
boolean, so `sum(is_correct)` returned `True` where a count was expected and every solved count came
out as 1. `cast(..., Integer)` before the `sum` fixes it on both dialects. It was caught by a test
that recorded two solved questions and expected 2.

## Where they appear

- `/users/<username>` — the full set, public to signed-in members, with the definition of the capped
  average underneath.
- `/profile` — questions, answered, favourites, plus a link to the full page.
- `/library` — answered and overall rate in the header.

## The user page

`/users/<username>` resolves by username **or** by uid. Everything in the interface links by uid,
because that survives a username change; the username form works for a hand-typed or bookmarked URL.

| Viewer | What the page offers |
|---|---|
| The member themselves | the metrics, plus "Edit your profile" |
| Any other active member | the metrics, read-only |
| A banned or revoked member | `404`: their numbers are not public once access is gone |

You reach it from three places, all of them the same link: the author's name on a question card, the
avatar beside it, and your own chip in the navbar.


## Topic breakdown

The member page carries a per-topic table: attempted, solved, accuracy and the
first-try rate, for every topic that has at least one attempt. It is computed on
read from the attempt rows (`metrics.topic_mastery`), not cached per topic: a
per-topic cache would have to be invalidated by every edit that deletes attempts,
and the aggregate is one query.

Topics with no attempts are left out. A row reading "0 of 0" says nothing, and the
page is about what has been tried.

The breakdown is **public by default**. The account page has a switch,
`users.progress_private`, which hides it from everyone but its owner — including
the administrator, who sees the same page a member does. It is stored as
`progress_private` rather than `progress_public` so a newly added boolean column
backfills to the public state.
