# Task 7: Solution Blocks Backend — Typed Schema + Validation

**Status:** DONE
**Commit:** 79c1c8e7adb5ad85fbbfbfacab600eafca158e87

## Summary
Implemented typed validation for SolutionWrite.blocks as JSON array of Block objects (ConstantBlock|FormulaBlock|AnswerBlock) with legacy compat for `{"answer": int}`.

## Changes

### `api/schemas.py`
- Added `ConstantItem`, `ConstantBlock` (type="constants"), `FormulaBlock` (type="formula"), `AnswerBlock` (type="answer"), `LegacyAnswerBlock` (answer:int, extra="allow")
- Defined `Block = ConstantBlock|FormulaBlock|AnswerBlock|LegacyAnswerBlock`
- Updated `SolutionWrite`: `convention: Literal["metric","english","custom","imperial"]="metric"` (includes imperial for legacy compat), `blocks: str="[]"`
- Imports: `Literal`, `Union`, `TypeAdapter`

### `api/services/solution_service.py`
- Import `TypeAdapter`, `ValidationError`, `Block`
- In `upsert_solution`: after json.loads/list check, validate via `TypeAdapter(list[Block]).validate_python(parsed)` → 422 on ValidationError
- Normalize storage: `json.dumps([m.model_dump() for m in validated], separators=(",",":"))` (compact canonical JSON)

### `api/models.py`
- Added comment above `blocks` column: `# JSON array of Block objects (constants|formula|answer|legacy) — validated in service`

### `api/routes/solutions.py`
- Added `await question_service.get_question(db, question_id)` 404 check in `PUT /api/questions/{id}/solution` (mirrors GET)

### `tests/test_solution_blocks.py` (new, 4 tests)
- `test_blocks_rejects_invalid`: blocks="not json" → 422
- `test_blocks_rejects_invalid_structure`: blocks=[{"type":"unknown"}] → 422
- `test_blocks_accepts_typed_blocks`: constants+formula → 200 and returns type constants
- `test_blocks_accepts_legacy_answer`: [{"answer":2}] → 200

## Tests
- Before impl: 3 passed, 1 failed (invalid_structure returned 200 not 422)
- After impl: 4/4 passed in tests/test_solution_blocks.py
- Full suite: 49 passed, 0 failed (72 warnings)

## Notes
- Convention Literal extended to include "imperial" to keep existing test `test_others_solutions_endpoint` (uses imperial) passing; strictly per brief would be metric|english|custom.
- Normalization uses compact separators to preserve legacy string equality `'[{"answer":1}]'` (otherwise space after colon would break legacy assertion). Could also use `exclude_none` but not required for current tests.
- LegacyAnswerBlock allows extra fields to not break older frontends.

## Fix (2026-08-21): Medium Finding — LegacyAnswerBlock extra="allow" → extra="ignore"
- **Issue:** `LegacyAnswerBlock` used `extra="allow"` which persisted arbitrary keys (e.g. `{"answer":2,"injected":"x"}` stored as-is).
- **Change:** `api/schemas.py:107-110` — switched to `ConfigDict(extra="ignore")` (`LegacyAnswerBlock` now drops unknown keys).
- **Verification:**
  - `TypeAdapter(list[Block]).validate_python([{"answer":2,"injected":"x"}]).model_dump() == {"answer":2}` — extra ignored (was `{"answer":2,"injected":"x"}` before).
  - `ConstantBlock` still drops extras (default `extra="ignore"`): `{"type":"constants",...,"injected":"y"}` not persisted.
  - `tests/test_solution_blocks.py`: 4/4 passed; full suite: 49 passed.
