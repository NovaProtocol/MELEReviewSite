# MELE Review

<div align="center">

![MELEReviewSite](https://github.projectnova.download/public/project/mle-review.svg)

</div>

A study companion for the Mechanical Engineering licensure exam.

Reviewing for the board exam means working through hundreds of multi-step problems where a single unit
mistake ruins the answer. This is a reviewer that does the arithmetic properly, explains where a
solution went wrong, and keeps track of what still needs work.

It exists because a bare answer key is not enough. Knowing the correct letter does not teach the
method, and the method is what the exam tests.

## What it does

**An equation solver that respects units.** Formulas are solved with real dimensional analysis across
both metric and English conventions. A result in the wrong unit is flagged rather than quietly
accepted, which is the mistake that costs the most points in a timed exam.

**A question bank that grows.** Questions are added and organised by topic, and each one keeps a
worked solution rather than only a correct answer. The bank is maintained by hand, so it reflects the
topics that actually appear.

**Solutions that explain themselves.** A solution is built from typed blocks, so an explanation can
mix prose, typeset mathematics, and diagrams instead of being squeezed into one block of plain text.
Reading it looks closer to a worked example in a textbook than to a comment in code.

**Feedback that explains.** A wrong answer shows the reasoning and identifies where the method
diverged, rather than only marking it wrong.

**Flags and progress.** Questions can be marked to come back to later, and progress is tracked per
topic, so revision time goes where it is needed instead of where it is comfortable.

**Schema changes that can be reversed.** Database changes ship as versioned Alembic migrations, so a
running installation can be upgraded in place without rebuilding the data by hand.

## Running it

```bash
cp .env.example .env
# then fill in the values it documents, and start the stack
docker compose up -d --build
```

The reviewer is at `/`, and the admin area at `/admin/`.

## Documentation

Full documentation is served by the stack at `/documentation/`, and the sources are in
[`documentation/docs`](documentation/docs).


## License

BSD 3-Clause. See [LICENSE](LICENSE).
