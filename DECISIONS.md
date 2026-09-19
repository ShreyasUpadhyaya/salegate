# DECISIONS.md

Short decision log. Each entry: context, decision, consequence. Status is Proposed until confirmed on build day.

## D1. Build the QA gate, not the voice agent
Context: two briefs, 6 real build hours, solo. Decision: QA automation. It is batch, testable and demoable offline,
and fits deterministic rule engines with audit trails. Consequence: the demo depends on one recording and synthetic data, not live telephony.

## D2. Deepgram pre-recorded REST through httpx
Context: need speakers, word timings and card redaction in one call, fast, on a laptop with no CUDA GPU.
Decision: Deepgram nova-3 via plain REST (no SDK, fewer version surprises). Consequence: depends on network; transcripts cached by audio hash.

## D3. Channels over diarization when available
Context: call-centre recordings are often stereo, one channel per party. Decision: if ffprobe shows 2 channels use multichannel,
else diarize and map speaker 0/1 to agent/customer by who reads the disclaimer. Consequence: fewer speaker errors on stereo audio.

## D4. Deterministic first, LLM last
Context: critical checks must essentially never false-pass. Decision: fuzzy matching, regex and extractors decide most checks.
The LLM only adjudicates unresolved semantic checks, cites utterance ids that are validated, and is cached.
Consequence: explainable, cheap, reproducible scores. LLM failure lowers automation, never safety.

## D5. Uncertainty routes to a human
Decision: low STT confidence or borderline match turns PASS/FAIL into REVIEW. Any critical REVIEW sends the sale to QA.
Consequence: slightly more human work, no uncertain auto-pass, no manufactured criticals from mishears.

## D6. Check library versioned by effective date
Decision: each check row has version, effective_from, effective_to. The scorer resolves by call date and stores a snapshot hash.
Consequence: rescoring an old call gives the same answer even after the checklist changes.

## D7. Redact card data at source
Decision: Deepgram redact=pci plus a local Luhn pass before storage. Presence of a redaction token raises a violation flag.
Consequence: digits never exist in our database or UI.

## D8. Append-only overrides
Decision: overrides are a separate table, never updated. Effective status is the latest override. Agreement rate uses it.
Consequence: full audit trail, and a direct measure of model calibration.

## D9. SQLite and Streamlit
Decision: SQLite file DB and Streamlit UI on top of FastAPI. Consequence: zero infra, fast iteration. Production would swap in Postgres and the CRM's own UI.

## D10. Reproducible 5% sample
Decision: sample clean calls by hash of lead id, not random. Consequence: the same lead is always sampled or not, which makes audits reproducible.

## D11. Real recording stays out of the public repo
Context: the test recording is a real sales call and the repo is public. Decision: gitignore handout/, audio and derived transcripts. See D13 for the full policy on how the recording is used and written up.

## D12. Dashboards run on seeded history
Context: one real call cannot show weekly trends. Decision: seed_history.py generates synthetic scored leads, labelled as seeded demo data in the UI.

## D13. How the real test recording is handled
Context: CIMET hands out one real sales call recording as build material ("hear exactly how agents talk"). This is
provided for exactly this purpose, so using it locally to build and to demo live, in front of CIMET's own judges, needs
no extra sign-off. The only real exposure is the public GitHub repo and anything shared as a link after the event,
since that can outlive the room and reach people who never consented to seeing this customer's details.
Decision, split by surface:
- Local build and the live in-room demo: use the real recording freely. Transcribe it, score it, play it back, show
  the real transcript on screen. This is the intended use of the file CIMET gave us.
- Public repo: the audio file and its full transcript are gitignored, always. `results/agreement.md` and any
  committed evidence text quote check outcomes and confidence, never the customer's actual email, phone, DOB or
  address; values are masked (`j.smith@gm***`) or the line is paraphrased ("email read-back differs from CRM by one
  character") instead of reproduced. Aggregate numbers (agreement rate, count of criticals) are not PII and are fine to commit.
- Backup video: recorded against a synthetic lead only, never the real recording, so the link can be shared without
  carrying any real customer's voice or data outside CIMET's room.
Consequence: nothing here depends on a mentor confirming anything mid-event; the policy is decided and encoded in
`.gitignore`, in how results are written, and in which lead the backup video uses.

## D14. Pre-event spike informs, never ships
Context: the night before, a throwaway rehearsal proved the check-engine approach against CIMET's own
worked example and caught a real span-isolation bug in the email extractor. Decision: keep it in the
repo under `reference/spike/` for context, but the real app never imports it; Phase 6 to 8 port the
logic into `app/checks/` with proper types and fresh tests written on build day. Consequence: build day
work is still fully live and onsite, and starts from a design already known to work rather than one
being invented from scratch under the clock.

## D15. Build starts before the handout arrives
Context: at Phase 0 the `handout/` folder was empty, so the recording, lead dataset, check-library export
and sandbox payload could not be inspected. Waiting would burn the morning. Decision: split Phase 0 into
0a (repo and scaffolding, unblocked) and 0b (handout inspection, runs when the files land).
`docs/data_notes.md` is written as a fill-in checklist with explicit TO FILL markers rather than guessed
field names, and if the files are still missing at Phase 5 the check library is seeded from the spike's
six checks against a synthetic lead, labelled synthetic in the UI. Consequence: every phase before 5 is
genuinely unblocked, no invented field names reach the code, and the loader reads from the library table
either way so the real export drops in without a rewrite.

## D16. A/B/C classification is ours, not CIMET's
Context: the check type drives which evaluator runs, but the export is unlikely to carry a type column.
Decision: the library loader classifies each row on load (script text means A, a named CRM field or value
means B, behavioural means C) and maps the export's severity column onto our two separate booleans,
`critical` (a FAIL holds the sale) and `fatal` (the score also goes to zero). The resulting mapping table
is written into `docs/data_notes.md`. A row that resists classification defaults to Type A with a
REVIEW-biased threshold and is flagged, never silently dropped. Consequence: the classification is
auditable in a document rather than buried in code, and a mis-typed check surfaces as REVIEW, not a
false PASS.
