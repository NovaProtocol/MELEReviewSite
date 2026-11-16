# Quiz Mode

`/quiz` builds a timed paper out of the bank and runs it.

## The bank a topic offers

Each topic offers its **top 1000 questions by vote score**, or everything it has if
that is fewer. The builder shows the bank size next to the topic, and a count box
that says how many of them to take; the take is a random sample of the pool, so two
quizzes from the same topic are not the same quiz.

Filters narrow the pool before the sample:

| Filter | Effect |
|---|---|
| Question kind | any, identification only, or computation only |
| Only what I have not answered | drops questions with an attempt from this member |
| Only my favourites | keeps what the member starred |

Computation questions are identified by a tag rather than by reading the text. A
heuristic over the statement would be wrong in both directions, and a tag is the
one thing an author can be certain about.

## Order

| Setting | What it does |
|---|---|
| Shuffle everything | one shuffled list |
| Group by topic | contiguous per-topic runs, topic order and each run shuffled |
| Group by subject | contiguous per-subject runs, shuffled inside |

## The code

A quiz is not stored. The code holds the settings and the question ids **in order**,
zlib-compressed and base64url-encoded:

```
{"v":1,"s":{"timer_minutes":30,"group":"mixed","title":"","filters":{...}},"q":[41,7,88,...]}
```

`/quiz?code=<code>` reopens the same paper, so a contest needs no lobby and no
database row: whoever has the code answers the same questions in the same order.
Nothing about the code is secret; it is a paper, not a result.

## Running it

One question at a time, answered by clicking a choice or pressing A-E. The answer
sheet is a bubble sheet: every question is a numbered row with A-E bubbles, so a
paper can be answered without leaving it, and clicking a number jumps to that
question. Arrows move, the clock counts down, and the paper submits itself when
the time is up.

**Auto next** is off by default. Turned on, answering moves to the next question,
which is what a rapid pass wants. **Copy quiz link** puts the shareable address on
the clipboard; the code itself is not printed, because nobody reads it.

**Right-click a choice** to cross it out, on the question or on the sheet. Crossed
choices show red and struck through, and the same click takes the marking back. A
quiz's crossings are not stored: the paper is a sitting, not a record.

## Scoring

Submitting records each answer as an ordinary attempt, so a quiz moves the same
numbers the profile shows: first selection kept, a correct answer locking the
sheet, each try costing an attempt. A question already answered correctly is not
re-answered, and is reported as "already solved" rather than counted again.

The score is correct over answered, and blank questions are not counted one way or
the other. That is deliberate: a paper left half-finished should not read as 0%.

## One at random

`POST /api/quiz/random` takes the same filters plus a subject and an exclude list,
and returns one question for the page to open. The draw is made in the application
from a capped sample, because `random()` is SQLite and `RAND()` is MySQL.
