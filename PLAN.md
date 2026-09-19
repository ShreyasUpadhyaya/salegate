# PLAN.md: CIMET QA Automation build

Build window 09:30 to 16:00. Target: final deliverable pushed and tagged by 15:30.
Break 13:00 to 14:00 is optional; building continues through it.

## The one line
No sale ships unscored. Every lead's call is ingested by API, transcribed with speakers and word timings,
scored against the retailer checklist version that was live on the call date, gated, and explained with
the exact transcript line and audio timestamp.

## Reality check on scope
The handout assumes 12 hours. We have 6. So: one retailer (the one in the check-library export),
its full checklist, all three check types, the gate, one strong review screen, dashboards on seeded data.
Depth on one path beats breadth.

## Judging criteria mapped to what we build
| Criterion (weight) | What we build | Proof we show |
|---|---|---|
| Scoring accuracy (30%) | Deterministic matchers first, confidence-aware, critical checks never pass without evidence | `results/agreement.md`: agreement vs hand labels, critical false-pass count |
| Coverage (25%) | Type A verbatim, Type B factual, Type C behaviour, full checklist of one retailer | Lead review screen lists every check with status |
| Traceability (20%) | Evidence contract on every result: utterance id, text, start/end seconds, check id, check version | Click a failed check, audio plays at that second, version shown |
| Gate and escalation (15%) | AUTO_SUBMIT / HELD_TL / QA_REVIEW, 5% clean sample, submit endpoint refuses unscored leads | Live: submit before scoring returns 409 |
| Guardrails and judgment (10%) | Low-confidence routing, PCI redaction, consent as a check, overrides logged, no auto-correction | Crosstalk/mishear/silence tests pass without false criticals |

## Architecture
Audio source: `data/recordings/demo/call.wav`, self-recorded from our own script, single channel,
diarized. CIMET provided no recording, only `handout/transcript.pdf`. See DECISIONS D17.
```
dialler_sim.py --POST--> /api/dialler/recordings (lead_id, call_started_at, agent_id, audio)
                              |  202 Accepted, idempotent on lead_id + sha256(audio)
                              v
                    data/recordings/<lead_id>/<sha>.wav  (gitignored)
                              |  background task
                              v
                 Deepgram pre-recorded REST (nova-3, diarize=true, single channel,
                 utterances, smart_format, redact=pci, keyterms)  -> cache/deepgram/<sha>.json
                              v
                 transcripts: utterances(speaker, start, end, text, confidence) + words
                              v
     scorer: resolve check-library version by call date -> run A, B, C evaluators
             -> CheckResult rows with evidence -> gate decision
                              v
            SQLite (data/app.db)  <-- overrides (append-only)
                              v
     FastAPI endpoints  <-->  Streamlit: Lead review | Queues | Dashboards
```

## Data model (SQLite via SQLAlchemy 2.0)
- `leads`: lead_id, retailer, agent_id, tl_id, site, campaign, call_started_at, crm_fields (JSON), plan_code, status
- `recordings`: id, lead_id, sha256, path, channels, duration_s, received_at, state (RECEIVED, TRANSCRIBING, TRANSCRIBED, SCORED, FAILED)
- `utterances`: id, recording_id, idx, speaker (agent/customer/unknown), start_s, end_s, text_redacted, avg_confidence
- `words`: utterance_id, word, start_s, end_s, confidence (store only if time allows; utterances are enough for evidence)
- `check_library`: check_id, version, retailer, type (A/B/C), critical, weight, fatal, definition (JSON), effective_from, effective_to, content_hash
- `scores`: id, lead_id, recording_id, library_snapshot_hash, scored_at, decision, sampled_for_qa, score_with_fatal, score_without_fatal
- `check_results`: score_id, check_id, check_version, status (PASS, FAIL, REVIEW, NOTE, NA), confidence, method, reason, evidence (JSON list)
- `overrides`: id, check_result_id, auditor, old_status, new_status, reason, created_at (never updated or deleted)

## Evidence contract (every CheckResult)
`check_id, check_version, status, confidence (0 to 1), method (fuzzy|regex|extract|timing|llm), reason (one plain sentence),
evidence: [{utterance_id, speaker, start_s, end_s, text_redacted}]`.
A PASS with empty evidence is a bug. Tests enforce it.

## Check logic in brief (full detail in the qa-check-engine skill)
- A, verbatim/script: normalise text, slide a window over agent utterances, rapidfuzz `partial_ratio` + `token_set_ratio`.
  >= 88 PASS, 72 to 88 REVIEW, < 72 FAIL. Low STT confidence on the matched span downgrades PASS/FAIL to REVIEW.
  Consent disclaimer must occur before any data is collected (time-ordered check).
- A, semantic (e.g. "account holder confirmed"): keyword/regex first; LLM adjudicator only if unresolved, one batched call per lead,
  must cite utterance ids that exist, cached on disk. LLM unavailable means REVIEW, never PASS.
- B, factual: extractors for rates (cents per kWh, peak/off-peak/shoulder/supply), email (spoken forms like "j dot smith at gmail dot com"),
  DOB, address, NMI/MIRN, move-in date, concession, life support, gift card. Compare transcript value vs CRM field vs plan rate card.
  Mismatch with high confidence FAIL; with low confidence REVIEW. GST-inclusive vs exclusive ambiguity goes to REVIEW, not FAIL.
- C, behaviour: from timings only. Dead air (gap > 20 s between any speech), interruptions (overlap > 1 s across speakers),
  talk ratio. Always NOTE, never blocks.

## Gate
1. Any critical FAIL -> HELD_TL (TL queue).
2. Else any critical REVIEW -> QA_REVIEW (QA queue). Nothing uncertain auto-passes.
3. Else AUTO_SUBMIT, and 5% sampled to QA by `int(sha256(lead_id)[:8],16) % 100 < 5` (reproducible).
4. `POST /api/leads/{id}/submit` returns 409 if unscored or held. This is the "no sale ships unscored" proof.

## Guardrails mapped to implementation
| Handout constraint | Implementation |
|---|---|
| Test data only | Only CIMET synthetic leads and provided files. Our own recording carries no real customer, so it is ours to commit or publish (D17). |
| Consent is a check | Recording disclaimer is a critical Type A check with an ordering rule. Recording existence proves nothing. |
| No card data surfaced | Deepgram `redact=pci` at source plus a local Luhn regex pass before storage. Redaction token present -> violation flag, digits never stored. |
| No advice, no auto-correction | Read-only on CRM fields. The system reports and holds. No writes to leads except status. |
| Rules that were live | Check versions have effective_from/to. Scorer resolves by call_started_at. Snapshot hash stored on the score. |
| Respect the override | Append-only overrides table. Effective status = latest override else model status. Agreement rate computed from it. |

## Repo layout
```
app/            main.py, config.py, db.py, models.py
app/ingest/     dialler.py (endpoint), transcribe.py (Deepgram), redact.py
app/checks/     library.py (load + versions), normalise.py, verbatim.py, factual.py, behaviour.py, llm_adjudicator.py
app/scoring/    scorer.py, gate.py, sandbox.py (adapter: our statuses to the sandbox payload, edge only)
app/api/        leads.py, scores.py, overrides.py, dashboards.py
ui/             Home.py, pages/1_Lead_review.py, 2_Queues.py, 3_Dashboards.py, theme.py
scripts/        dialler_sim.py, seed_history.py, eval_agreement.py, reset_db.py
tests/          test_normalise.py, test_verbatim.py, test_factual.py, test_gate.py, test_guardrails.py
handout/        transcript.pdf and any later CIMET files (gitignored)
results/        agreement.md, scored_leads.json, screenshots/
docs/           data_notes.md, architecture.png (optional)
reference/      spike/, tonight's rehearsal code, port from it, never import it, never ship it
```

## Schedule and commit plan
Commit messages: plain English, max 2 lines, no prefixes, no trailers. Nothing is committed before 09:30.

| Time | Work | Done when | Commit message |
|---|---|---|---|
| 09:30 to 09:45 | Phase 0a: create GitHub repo, drop in CLAUDE.md, PLAN.md, DECISIONS.md, .gitignore | `docs/data_notes.md` drafted | `Start the project with the plan, decision log and data notes` |
| when files land | Phase 0b: inspect handout, fill every TO FILL in `docs/data_notes.md` | No assumption in data_notes survives a real file | `Record what the CIMET handout files actually contain` |
| 09:45 to 10:05 | uv project, FastAPI skeleton, config from .env, SQLite models | `/health` returns ok, tables create | `Set up the FastAPI app, config and SQLite models` |
| 10:05 to 10:30 | Dialler endpoint, idempotent storage, simulator script | Simulator posts a file and a recording row appears | `Accept dialler recordings by API and store them against the lead` |
| 10:30 to 10:55 | Deepgram transcription in background task (diarize=true), cache, utterances saved | Self-recorded call transcribed with speakers and timings | `Transcribe calls with Deepgram and keep speakers and word timings` |
| 10:55 to 11:05 | Redaction pass, PCI flag | Test with a fake card number string passes | `Redact spoken card numbers before anything is stored` |
| **11:05 checkpoint** | Ingestion works end to end with zero manual steps. If not, fall back to provided transcripts and fix later | | |
| 11:05 to 11:30 | Check library loader: parse, classify each row A/B/C, map severity to critical and fatal, versions and effective dates | Loads CIMET export, resolves version by date, classification table written into `docs/data_notes.md` | `Load the retailer check library with versions by effective date` |
| 11:30 to 12:00 | Type A verbatim and ordering, normalisers | Disclaimer and DMO checks score on test call | `Score script checks by matching agent speech to approved text` |
| 12:00 to 12:35 | Type B extractors and comparisons vs CRM and rate card | Rate and email mismatches caught with evidence | `Compare quoted rates, email and dates with CRM and the rate card` |
| 12:35 to 12:50 | Type C timing notes | Dead air and interruptions listed as notes | `Add dead air, interruption and talk ratio coaching notes` |
| 12:50 to 13:10 | Gate, sampling, submit refusal | Gate unit tests pass | `Hold sales on critical fails and send unsure checks to QA` |
| 13:10 to 13:30 | API endpoints: scores, gate, submit, overrides | Swagger shows all routes working | `Expose scoring, gate, submit and override endpoints` |
| 13:30 to 14:15 | Streamlit lead review: verdict, timeline strip, click-to-play, transcript | Clicking a failed check plays audio at that second | `Build the lead review screen with click-to-play timestamps` |
| 14:15 to 14:30 | Override flow in UI, history shown | Override logged, effective status updates | `Log auditor overrides and show the score history` |
| 14:30 to 14:50 | Seed history, dashboards and queues | FPY, critical fail rate, repeat offenders render | `Add queues and dashboards by agent, retailer, campaign and TL` |
| **14:50 feature freeze** | No new features after this line | | |
| 14:50 to 15:05 | Hand labels, eval script, results files (mask real customer values per DECISIONS D13) | `results/agreement.md` generated, no raw PII in it | `Measure agreement with hand labelled calls and save the results` |
| 15:05 to 15:15 | Messy-call tests: crosstalk, mishear, silence | Tests green | `Add tests for crosstalk, mishears and silence` |
| 15:15 to 15:25 | README, run steps, DECISIONS.md final pass, screenshots | Fresh clone runs with README steps | `Write the README, run steps and final decision notes` |
| 15:25 to 15:30 | Reset DB, seed, final run, tag `v1.0` | Tag pushed | `Final demo data and results snapshot` |
| 15:30 to 16:00 | Record backup video, rehearse demo twice | Video link ready | (optional) `Add the demo video link to the README` |

~~Optional: send unresolved semantic checks to Gemini~~ Cut at 12:20, see the cut list.

## Reference: tonight's rehearsal spike (`reference/spike/`)
Before build day, the riskiest logic was pressure-tested against CIMET's own worked example
(Lead 3613790, Retailer 1: rate 28.6c vs plan 31.9c, email gmail.com vs CRM's gmial.com, a 47s dead air).
This is proof-of-approach, not app code. Port it into `app/checks/` with proper types, module boundaries
and tests per CLAUDE.md; do not import it directly or commit it into the real app.

Note on audio: the spike's fixtures assume utterances that already carry speaker labels and timings.
That now comes from Deepgram diarization of our own recording (`data/recordings/demo/call.wav`,
single channel, D17), not from a CIMET-provided file. The spike logic is unaffected, since it starts
from utterances either way, but the two bugs below matter more now: diarization can mis-split a turn,
so span isolation and continuous fixtures are what keep that from becoming a false critical.

**Already settled, do not re-derive:**
- rapidfuzz thresholds 88 PASS / 72 REVIEW / below FAIL work for script checks (disclaimer, account
  holder, DMO all passed cleanly at those thresholds).
- The rate extractor (regex near tariff words, tolerance 0.05c) correctly catches the mismatch with
  both values in the reason string.
- The gate correctly holds for TL the moment any critical check fails, and lists which ones.
- "Every PASS carries non-empty evidence" is a real, checkable invariant; keep it as a test.
- Test evidence timestamps, not only status. Review caught script checks all citing 12s while tests stayed green (bug 3 in README-SPIKE.md). Ties in window matching go to the shortest window.

**Two bugs already found and fixed, carry the fix forward, do not reintroduce:**
1. Spoken-value extractors (email, and likely address, DOB) must isolate the relevant span with a
   targeted regex BEFORE normalising, never find-and-replace across the whole utterance. The fixed
   pattern is in `reference/spike/normalise.py` (`_EMAIL_SPAN`). Apply the same span-isolation
   principle to every Type B extractor in Phase 7, not just email.
2. Dead-air and other timing checks need a continuous transcript to behave sensibly; sparse or
   highlight-only fixtures produce fake gaps. When writing Type C tests in Phase 8, build fixtures with
   continuous back-to-back utterances, not just the highlighted moments.

Phases 6, 7 and 8 should open `reference/spike/verbatim.py`, `factual.py` and `gate.py` first.

## Review checkpoint
Once a phase is committed, code and test output can be shared back for review: what changed, whether it
holds the hard rules in CLAUDE.md, whether the evidence contract and gate logic are intact, and whether
it actually runs. This is a second pass, not a replacement for testing before each commit.

## Fallback if the handout arrives late or not at all
Partly resolved: CIMET confirmed the handout is a PDF transcript and no recording (D17). The audio
fallback is gone because we make the audio ourselves. What follows still applies to the check library
and lead data.
Phases 5 to 7 need a check library and a lead. If `handout/` is still empty when Phase 5 starts, seed the
library from the spike's six checks (Retailer 1, all three types) and use a synthetic lead, both labelled
as synthetic in the UI and the README. Every mechanism still demos end to end: only the data provenance
changes. Swap in the real export the moment it lands, since the loader reads from the table either way.

## Cut list, in order, if behind
1. Word-level table (keep utterances only).
2. ~~Docker compose~~ **CUT at 12:20.** Never started, nothing depends on it.
3. ~~LLM adjudicator~~ **CUT at 12:20.** Unresolved semantic checks go to REVIEW instead, which is the
   behaviour hard rule 10 already requires when the LLM is unavailable. `llm_enabled` stays false.
   Time reclaimed after Phase 3 ran over on speaker recovery (DECISIONS D18).
4. Campaign/site rollups (keep agent and retailer).
5. Never cut: ingestion, gate, evidence contract, click-to-play, overrides log, agreement results.

## Claude Code budget (Pro plan)
- Model: Sonnet for everything. Keep effort normal. Use plan mode only for phase starts.
- `/clear` after each committed phase. PLAN.md and DECISIONS.md carry the context, not the chat.
- One phase per prompt. Ask for diffs and a test run, not explanations.
- Do not use claude.ai chat during the build; it shares the same usage pool.
- If the limit hits: continue the current phase in Cursor or Codex using the same CLAUDE.md as context.

## Phase prompts (paste one at a time after /clear)
0. First prompt of the day, in plan mode, after keys and `.env` are in place (full version with all
   readiness checks is in SETUP.md step 10):
   `Read CLAUDE.md, PLAN.md and DECISIONS.md fully, including the Reference section pointing at
   reference/spike/. Then inspect every file in ./handout: the call recording (use ffprobe for duration,
   channels, sample rate), the synthetic lead dataset, the check-library export and the scoring sandbox
   payload. Do not write application code yet. Write docs/data_notes.md with: a file inventory, formats
   and fields, how the check-library export maps to our CheckDefinition model, what the sandbox payload
   expects, whether transcripts have timestamps and speakers, and a list of gaps and assumptions. Then
   propose any changes to PLAN.md as a short list and wait for my OK. After I approve: git init, create
   the public GitHub repo with gh, add .gitignore, and make the first commit using commit-cadence.`
1. `Phase 1 from PLAN.md: uv project, FastAPI skeleton, config, SQLite models. Follow CLAUDE.md. Show the diff summary and run the app once.`
2. `Phase 2: dialler endpoint + simulator. Idempotent on lead_id and sha256. Add a test. Then commit using commit-cadence.`
3. `Phase 3: Deepgram transcription as a background task with disk cache. Use diarize=true (our recording is
   single channel, see D17). Save utterances. Run it on data/recordings/demo/call.wav once.`
4. `Phase 4: redaction pass and PCI flag with tests.`
5. `Phase 5: check library loader with versions. Map the CIMET export fields using docs/data_notes.md.`
6. `Phase 6: Type A evaluators using the qa-check-engine skill. Score the test call and print a results table.`
7. `Phase 7: Type B extractors and comparisons. Reproduce the lead 3613790 style mismatches in a test.`
8. `Phase 8: Type C timing notes, then the gate and submit refusal with tests.`
9. `Phase 9: API routes for scores, gate, submit, overrides.`
10. `Phase 10: Streamlit lead review page using the qa-console-ui skill and the frontend-design plugin. Take a screenshot, critique it against the skill, fix the top 3 issues.`
11. `Phase 11: overrides in UI, seed_history.py, queues and dashboards.`
12. `Phase 12: eval_agreement.py, messy-call tests, README from the template, final commit and tag.`
