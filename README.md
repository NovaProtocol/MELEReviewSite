# MELE Review

<div align="center">

![MELEReviewSite](https://github.projectnova.download/public/projects/mle-review.svg)

</div>

A study companion for the Mechanical Engineering licensure exam.

Reviewing for the board exam means working through hundreds of multi-step problems where one unit
mistake ruins the answer. This is a reviewer that does the arithmetic properly, explains the answer,
and keeps track of what still needs work.

## What it does

- **An equation solver that respects units.** Formulas are solved with real dimensional analysis,
  across both metric and English conventions, so a result in the wrong unit is flagged rather than
  quietly wrong.
- **A question bank that grows.** Questions are added and organised by topic, and each one keeps a
  worked solution rather than just a correct letter.
- **Feedback that explains.** A wrong answer shows the reasoning and where the method went off,
  which is the part a bare answer key cannot do.
- **Flags and progress.** Questions can be marked to come back to, and progress is tracked per topic
  so revision time goes where it is needed.
- **Solutions that explain themselves.** A solution is a sequence of typed blocks, so an explanation
  can mix prose, typeset mathematics, and diagrams instead of being forced into one plain block of
  text.
- **Schema changes that can be reversed.** Database changes ship as versioned Alembic migrations, so
  a running install can be upgraded without rebuilding the data by hand.

## Running it

```bash
cp .env.example .env
# then fill in the values it documents, and start the stack
docker compose up -d --build
```

`.env.example` lists every variable. The reviewer is at `/`, and the admin area at `/admin/`.

## Documentation

Full documentation is served by the stack at `/documentation/`, and the sources are in
[`documentation/docs`](documentation/docs).
