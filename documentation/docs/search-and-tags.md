# Search and Tags

Two ways to find a question, because there are two different things people are
looking for.

**Browse** walks the taxonomy: subject, then topic. That is the default path and
it suits revision by syllabus.

**Search** is for when you remember a word but not where it lives, and **tags**
are for ideas that do not respect the syllabus at all.

## Why tags exist

The taxonomy is a tree. A question lives in exactly one topic, and a topic in
exactly one subject. Study is not a tree.

A question about differentiating to find a velocity belongs under kinematics, and
one about a derivative at a point belongs under differential calculus. A member
revising `derivative` wants both, plus the one in economics. A tag is the only
structure that can say "these belong together" across the tree.

Tags are:

- **free-form**, created when a question carries one and reused by any other;
- **normalised on write**, so `Differential Equation`, `differential equation` and
  `differential-equation` are one tag rather than three;
- **multi-select**, and selecting several narrows the result (a question must
  carry every selected tag, not any of them);
- **cross-subject**, which is the point.

| Structure | Shape | Cardinality |
|---|---|---|
| Subject | one level | a question has exactly one |
| Topic | under a subject | a question has exactly one |
| Tag | flat | a question can carry many |

## Member search

`/search`. Deliberately **not live**: it runs on submit. A live search would hit
the database on every keystroke for every reader, and a review site has many more
readers than writers. The admin list next door is live for the opposite reason.

The form offers a keyword box, a subject dropdown and a tag checkbox fieldset. The
keyword matches the statement, every choice and the explanation.

### The tag hint

When a keyword also looks like a tag, the results carry a suggestion above them:

> There is a tag matching that word. Consider using tags instead: **rankine**

Each suggestion links to `/search?tags=<name>`, so the hint is one click from the
narrower result rather than advice. The hint only appears for tags that at least
one live question carries, so it never sends anyone to an empty list.

## Admin question list

`/admin`, Questions tab. This one *is* live, with a 250 ms debounce and a
request-generation guard so a slow early response cannot overwrite a later one.

| Control | Effect |
|---|---|
| Search | matches statement, choices and explanation as you type |
| Subject | narrows the topic dropdown, then filters |
| Topic | filters to one topic |
| Tag pills | multi-select, narrowing |
| Filter | all, visible only, negative score, hidden, deleted, nobody solved |
| Sort | newest, most answered, most attempts per question, lowest solve rate, lowest score |

Both "lowest" sorts are ascending, because the reason to sort that way is to put
the problems at the top.

## Deleted is not hidden

| State | On the site | In metrics | Row |
|---|---|---|---|
| Visible | shown | counted | kept |
| Hidden | hidden from members | **counted** | kept, restorable |
| Deleted | hidden from members | **not counted** | kept, restorable |

Hiding is a judgement about a question; the question is still the same question,
so the answers people gave still measure something. Deleting says the question
should never have counted, so it leaves everyone's numbers. Both keep the row, so
the administrator can see and restore either, and the audit trail survives.

`POST /api/admin/questions/{id}/delete` and `/restore` move a question between
those states and refresh the metrics of everyone who attempted it.
