# Quiz Mode

`/quiz` lists saved papers, `/quiz/new` builds one, and `/quiz/<uid>` is one paper.

## Why it is saved

A quiz used to be a code and nothing else. It is stored now, because it needs an
owner, a visibility, a life, and a record of who sat it. The address is short
enough to say out loud, which a code was not.

```
quizzes           id, uid, owner_user_id, title, description, settings,
                  is_private, scores_public, date_created, last_activity
quiz_questions    quiz_id, position, question_id
quiz_submissions  id, quiz_id, user_id, is_first_take, answers, score,
                  correct, total, duration_seconds, started_at, last_seen,
                  submitted_at
```

`settings` is JSON: timer, ordering, and the filters that were used. The questions
are rows in `quiz_questions`, in order, so a paper is a paper and not a query that
might come back different tomorrow.

## The bank a topic offers

Each topic offers its **top 1000 questions by vote score**, or everything it has if
that is fewer. Filters narrow the pool before the sample: question kind, what you
have not answered, your favourites. The take is a random sample of the pool, so two
papers from the same topic are not the same paper.

## Three rules

**A first take is permanent.** It is never overwritten, and opening the link again
shows it rather than starting over. Later sittings are practice: they are scored,
they do not replace the first take, and the sweep deletes them six hours after
their last update.

**Unlisted is not locked.** A private quiz is hidden from the list for everyone but
its owner and the administrator. The link still works for anyone who has it.

**A retired question closes the paper.** The slot keeps its question id, so the page
still shows what was asked, and Start is refused with the reason. The paper is not
silently rewritten.

## Lifetimes

| Rule | Value |
|---|---|
| Quizzes per account | 100, checked before a new one is made |
| Idle before a quiz goes unlisted | 7 days without activity |
| Practice sittings kept | 6 hours after their last update |
| Deleting a quiz | permanent, and takes every sitting with it |

Activity is a view, a start, or an answer. A ban deletes the banned member's quizzes
the same way, and their questions stay in the bank.

## Sitting one

Opening the link shows the landing page: the description, the leaderboard, and your
first take if you have one. **The clock starts on Start**, not on open. Answers are
saved as they are picked, so closing the tab loses nothing: the submission holds the
answers and the score is calculated from them.

The runner answers on screen or on the bubble sheet, arrows move, Auto next can be
switched on, and the paper submits itself when the clock runs out. Blank answers are
counted as wrong but the quiz still submits.

The result gives the score, correct over answered, overall time, average time per
question, and a review. Under it is a signature: a 21x21 grid drawn in the browser
from the quiz id, stable for that id, and not a QR code. Nothing about it is stored.

## Who sees what

| Viewer | Sees |
|---|---|
| Anyone with the link | the landing page, the paper, the leaderboard if it is public |
| The owner | the same, plus every sitting, with names and scores |
| The administrator | the same as the owner |

The quiz payload never carries an answer key. The key only comes back from
`/submit`, so a paper cannot be scraped for answers.
