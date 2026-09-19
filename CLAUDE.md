# CLAUDE.md

Project: automated QA gate for CIMET CRM sales calls (hackathon build, solo, 6 hours).
Every sale is scored against its retailer checklist before it can submit. Green goes through,
red is held with the failing check, transcript line and audio timestamp.

Read PLAN.md for scope, schedule and phase prompts, including the Phase 0 first prompt and the Reference
section. Read DECISIONS.md before changing any design choice. `docs/data_notes.md` describes the CIMET
handout files and field mappings. `reference/spike/` is proof-of-approach code from a pre-event rehearsal:
read it for the settled thresholds, the fixed span-isolation bug and the gate logic, then port the logic
into `app/checks/` with real types and tests. Never import it directly, never commit it into the app.

## Hard rules (never break)
1. Test data only for anything invented. Use the CIMET synthetic leads and provided files. Never invent real-looking PII.
2. The provided recording is real and is fine to transcribe, score and show live, since CIMET gave it to us for exactly
   that. It never leaves the room in written form: never commit the audio file, its full transcript, `.env`, `data/`,
   or `cache/`. Check `git status` before every commit. Any evidence text that reaches `results/` or a commit quotes
   the check outcome, not the customer's actual email, phone, DOB or address. See DECISIONS D13.
3. Never print, log or echo API keys. Read them from `.env` through `app/config.py` only.
4. Card numbers are redacted before storage (Deepgram `redact=pci` plus local Luhn pass). Digits are never stored, logged or shown.
5. The system never edits CRM fields, never rewrites the sale, never contacts a customer. It reports and holds.
6. Every CheckResult carries the evidence contract in PLAN.md. A PASS without evidence is a bug.
7. A critical check never PASSes on low confidence. Uncertain means REVIEW, which routes to QA.
8. Check versions resolve by the call date, not today. Store the library snapshot hash on each score.
9. Overrides are append-only. Never update or delete an override row.
10. Deterministic first. The LLM is only for unresolved semantic checks: batched per lead, cached on disk,
    must cite utterance ids that exist (validate them), and failure or rate limit means REVIEW.
11. Consent is a check. The recording disclaimer must be matched, and before any data collection.
12. Writing style for docs, UI copy and commit messages: plain sentences, no em dashes, never the word "perfect".

## Stack and commands (Windows, PowerShell)
- Python 3.12, uv, FastAPI, SQLAlchemy 2.0 + SQLite, pydantic v2, httpx, rapidfuzz, pandas, streamlit, plotly, pytest, ruff, python-dotenv, google-genai.
- Ask before adding any other dependency.
- Run API: `uv run uvicorn app.main:app --reload --port 8000`
- Run UI: `uv run streamlit run ui/Home.py --server.port 8501`
- Tests: `uv run pytest -q`   Lint: `uv run ruff check . --fix`
- Reset and seed: `uv run python scripts/reset_db.py; uv run python scripts/seed_history.py`
- Simulate the dialler: `uv run python scripts/dialler_sim.py --lead <id> --file <path>`
- Use `pathlib` everywhere (Windows paths). Use `127.0.0.1`, not `localhost`, in scripts.

## Code conventions
- Small pure functions in `app/checks/`. Evaluators take (check_definition, transcript, lead) and return CheckResult. No DB access inside evaluators.
- Thresholds live in `app/config.py`, not inline.
- Type hints everywhere, pydantic models at API edges.
- Each evaluator ships with at least one PASS test, one FAIL test and one REVIEW test.
- External calls (Deepgram, Gemini) go through one module each, with disk cache keyed by content hash. Never call them in a loop without cache.

## Workflow
- One PLAN.md phase per session. Start a phase in plan mode, then build.
- End of phase: `uv run ruff check . --fix`, `uv run pytest -q`, update DECISIONS.md if a choice was made, then commit via the commit-cadence skill.
- Keep replies short: what changed, test result, next step. No long explanations unless asked.
- Ask me before: schema changes after 12:30, deleting files, anything that spends API credit in bulk, or any deviation from PLAN.md.
- If blocked for more than 10 minutes, say so and propose the smallest fallback (for example, use provided transcripts instead of live transcription).

## Skills to use
- `qa-check-engine`: evaluators, normalisers, thresholds, test cases.
- `qa-console-ui`: Streamlit design system. Use together with the `frontend-design` plugin for every UI change.
- `commit-cadence`: how and when to commit.
