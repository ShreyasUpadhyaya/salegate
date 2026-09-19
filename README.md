# <repo-name>: score the sale before it ships

Every sale in CRM is scored against its retailer's checklist before it can submit.
All critical checks pass, it goes through untouched. Any critical fail, it is held with the exact
check, transcript line and audio timestamp. Anything uncertain goes to a human.

Built solo in 6 hours at the CIMET QA Automation hackathon, Jaipur. Uses synthetic data only.

<!-- screenshot of the lead review page: results/screenshots/lead_review.png -->
<!-- demo video link -->

## What it does
1. The dialler posts a recording by API, keyed on Lead ID. No manual download or upload.
2. The call is transcribed with speakers, word timings and card-number redaction.
3. The scorer loads the checklist version that was live on the call date and runs three kinds of checks:
   script (verbatim), factual (transcript vs CRM vs rate card) and behaviour (coaching notes).
4. The gate decides: auto-submit, hold for TL, or send to QA. 5% of clean calls are sampled to QA anyway.
5. TLs and auditors see why, click the timestamp, hear the moment, and fix or override. Overrides are logged.

## Results
See `results/agreement.md`. Fill in on the day:
| Metric | Value |
|---|---|
| Checks compared with hand labels | |
| Agreement | |
| Critical false passes | |
| Leads scored | |
| First-pass yield (seeded data) | |

## Run it
Requirements: Windows/macOS/Linux, Python 3.12, uv, ffmpeg, a Deepgram key (free credit).
```
git clone <repo-url>
cd <repo-name>
uv sync
copy .env.example .env        # then add DEEPGRAM_API_KEY (GEMINI_API_KEY optional)
uv run python scripts/reset_db.py
uv run python scripts/seed_history.py
uv run uvicorn app.main:app --port 8000
uv run streamlit run ui/Home.py --server.port 8501
uv run python scripts/dialler_sim.py --lead 3613790 --file <path-to-test-recording>
```
Open http://127.0.0.1:8501 and pick the lead. API docs at http://127.0.0.1:8000/docs.
Tests: `uv run pytest -q`.

## API
| Method | Path | Purpose |
|---|---|---|
| POST | /api/dialler/recordings | Dialler pushes a recording for a lead |
| GET | /api/leads/{id}/score | Latest score with every check and its evidence |
| GET | /api/leads/{id}/gate | Gate decision and reasons |
| POST | /api/leads/{id}/submit | Submits only if scored and not held (409 otherwise) |
| POST | /api/check-results/{id}/override | Auditor override, append-only |
| GET | /api/dashboards/agents | Rollups by agent and period |

## Check types
| Type | Compares | Blocks sale |
|---|---|---|
| A, script | Transcript vs approved script | Yes if critical |
| B, factual | Transcript vs CRM fields vs plan and rate card | Yes |
| C, behaviour | Transcript timings only | No |

## Guardrails
Test data only. Consent is checked, not assumed. Card numbers are redacted before storage. The system never edits the sale
or contacts a customer. Checks resolve to the version live on the call date. Overrides are logged, never dropped.

## Design decisions
See `DECISIONS.md`.

## Limitations and next steps
Fill in honestly on the day: one retailer covered, seeded dashboard history, thresholds tuned on few calls, and what you would do next.

## Repo layout
See `PLAN.md`.
