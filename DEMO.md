# DEMO.md: live demo, backup recording, Q&A, slides

Note on data: the live demo below uses the real CIMET recording, that is what it is for. The backup video in
section B uses a synthetic lead instead, so the shareable link never carries a real customer's voice or details.
See DECISIONS D13.

## A. Live demo run sheet (5 minutes)

### Before the judges arrive
1. `uv run python scripts/reset_db.py` then `uv run python scripts/seed_history.py`.
2. Terminal 1: API on 8000. Terminal 2: Streamlit on 8501. Terminal 3: ready with the dialler command.
3. Browser tabs: Streamlit lead review, http://127.0.0.1:8000/docs, GitHub repo, `results/agreement.md`.
4. Confirm the test recording transcript is already in cache (so a slow network cannot sink the demo).
5. Volume up, notifications off, zoom browser to 110%.

### The run
| Time | Do | Say |
|---|---|---|
| 0:00 | Show the handout line "No sale ships unscored" | "Today an auditor listens end to end and fills Excel. I moved that into the pipeline." |
| 0:20 | In Swagger, call submit on an unscored lead: 409 | "A sale cannot submit until it is scored. That is the gate." |
| 0:40 | Run the dialler simulator for the test lead | "The dialler pushes the recording by Lead ID. Nobody downloads anything." |
| 1:00 | Refresh: status moves to Scored | "Transcribed with speakers and word timings, card numbers redacted at source." |
| 1:20 | Open lead review: verdict sentence and timeline strip | "Held for TL. Red markers are critical fails, amber is needs review." |
| 1:45 | Click the failed rate check: audio plays at that second | "The TL hears 20 seconds, not 30 minutes. Quoted rate vs plan rate, side by side." |
| 2:15 | Point at check version and library hash | "Scored against the checklist that was live on the call date." |
| 2:35 | Show a REVIEW item from low confidence | "When the transcript is unsure, it goes to a human. Nothing uncertain auto-passes." |
| 2:55 | Show dead air note | "Behaviour checks coach, they never block a sale." |
| 3:10 | Save an override with a reason | "Auditors can overturn. It is logged, and it feeds the agreement rate." |
| 3:35 | Open a clean lead: Auto-submit, and one sampled to QA | "5% of clean calls still go to a human so we measure the model." |
| 3:55 | Dashboards: FPY, critical fail rate by check, repeat offenders | "Same critical failing 3 times in 7 days flags the TL." |
| 4:25 | Open results/agreement.md | "Agreement with my hand labels and critical false passes: X and Y." |
| 4:45 | Close | "No sale ships unscored, and the reason is one click away." |

### If something breaks
- Deepgram or wifi down: the transcript comes from cache; say so plainly.
- Streamlit crash: show the same data in Swagger `/api/leads/{id}/score`.
- Everything down: play the backup video.

## B. Backup recording script (about 4 minutes)

### Synthetic audio for the video
The video needs something to play when it hits a timestamp. Record a 20 to 30 second fake call yourself
(read two or three lines of a script, in two voices or with a friend) any time before 15:30, or generate
it with any TTS tool you already have. Save it as `data/recordings/demo/sample.wav`, gitignored either way,
and run the dialler simulator against that lead for the video instead of the real one.

### Tools on Windows
OBS Studio (free) for full-screen capture with mic, 1080p, 30 fps. Xbox Game Bar (Win+Alt+R) works for a single app window only.
Trim in Clipchamp. Upload to YouTube as Unlisted or Google Drive with link access, and put the link in the README.

### Shot list
Use a synthetic lead throughout, not the real recording, so the link is safe to share outside the room.

| Time | Screen | Narration |
|---|---|---|
| 0:00 to 0:20 | README top | Problem in one line and what the system does |
| 0:20 to 0:50 | PLAN.md architecture block | Dialler push, transcription, scorer, gate, UI |
| 0:50 to 1:10 | Terminal: dialler simulator run on a synthetic lead | Zero manual handling |
| 1:10 to 2:30 | Lead review page | Verdict, timeline, click failed check, audio plays, version shown, review item, note |
| 2:30 to 2:50 | Override save | Logged, not dropped |
| 2:50 to 3:20 | Dashboards | FPY, fail rate by check, repeat offenders |
| 3:20 to 3:40 | `app/checks/verbatim.py` and `factual.py` briefly | Deterministic first, evidence on every result |
| 3:40 to 3:55 | `results/agreement.md` and `DECISIONS.md` | Measured accuracy, decisions written down |
| 3:55 to 4:05 | Closing line | "No sale ships unscored." |

Files to open in the video, in order: README.md, PLAN.md, the UI, app/checks/verbatim.py, app/checks/factual.py,
app/scoring/gate.py, results/agreement.md, DECISIONS.md.

## C. Questions judges may ask

1. How accurate is it? Agreement with my hand labels on the calls I had, and the critical false-pass count. With more audited calls I would tune thresholds per check.
2. Why not just ask an LLM to score the call? Critical checks need to be reproducible and explainable. Fuzzy matching and extractors give the same answer every time with the exact line. The LLM only settles unresolved semantic checks and must cite real utterances.
3. What if the transcription is wrong? Low word confidence turns a pass or fail into needs review. Mishears go to a human, not into false criticals.
4. What about crosstalk and silence? Tested. Overlap lowers confidence, silence becomes a coaching note, neither blocks alone.
5. How do you know which speaker is the agent? Separate channels when the audio is stereo, otherwise diarization mapped by who reads the disclaimer.
6. How do you handle checklist changes? Versions with effective dates. The call date picks the version, and the score stores the snapshot hash.
7. How does consent work? The disclaimer is a critical script check with an ordering rule: it must come before data collection. A recording existing proves nothing.
8. What happens with card numbers? Redacted at transcription, double-checked locally, never stored. The score flags the violation.
9. Can an auditor disagree? Yes, with a reason. Overrides are append-only and drive the agreement rate.
10. Why 5% sampling of clean calls? To measure the model on calls it passed, since false passes are the costly error.
11. GST inclusive vs exclusive rates? If the quoted rate matches the plan with GST applied or removed, it goes to review, not fail.
12. How does it scale to 30 retailers and thousands of calls? Checks are data, not code. A new retailer is a new library export. Transcription is async, scoring is milliseconds per call, SQLite becomes Postgres and the background task becomes a queue worker.
13. Cost per call? Transcription is a fraction of a cent per minute, and the LLM is called only for unresolved checks, batched and cached.
14. What would you build next? Per-check threshold calibration from override data, the challenge workflow for agents, and real dialler webhook auth.
15. Why Streamlit? Fastest way to show a real review workflow in 6 hours. The API is the product; the CRM UI would call it.

## D. Short deck (only if asked), 6 slides
1. The bottleneck: manual listening, Excel, sales waiting. One line: no sale ships unscored.
2. Pipeline: dialler push, transcription, versioned checklist, scorer, gate.
3. Three check types and what blocks a sale.
4. Screenshot: lead review with timeline and click-to-play.
5. Accuracy and guardrails: agreement numbers, review routing, redaction, overrides.
6. What is next and how it scales.
