# DECISIONS.md

Short decision log. Each entry: context, decision, consequence. Status is Proposed until confirmed on build day.

## D1. Build the QA gate, not the voice agent
Context: two briefs, 6 real build hours, solo. Decision: QA automation. It is batch, testable and demoable offline,
and fits deterministic rule engines with audit trails. Consequence: the demo depends on one recording and synthetic data, not live telephony.

## D2. Deepgram pre-recorded REST through httpx
Context: need speakers, word timings and card redaction in one call, fast, on a laptop with no CUDA GPU.
Decision: Deepgram nova-3 via plain REST (no SDK, fewer version surprises). Consequence: depends on network; transcripts cached by audio hash.

## D3. Channels over diarization when available
Superseded by D17. Kept for the reasoning, which still applies if a second voice or a stereo source appears.
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
Overtaken by D17: there is no real recording, so nothing here binds. `handout/` stays gitignored anyway.
Context: the test recording is a real sales call and the repo is public. Decision: gitignore handout/, audio and derived transcripts. See D13 for the full policy on how the recording is used and written up.

## D12. Dashboards run on seeded history
Context: one real call cannot show weekly trends. Decision: seed_history.py generates synthetic scored leads, labelled as seeded demo data in the UI.

## D13. How the real test recording is handled
Overtaken by D17: CIMET provided no recording, so the customer-privacy split below is moot. The masking
habit for committed evidence text is worth keeping regardless, since it costs nothing.
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

## D17. We record the test call ourselves, and diarization is now primary
Context: at the opening ceremony CIMET confirmed no audio recording is provided. The handout is a redacted
PDF transcript with no timestamps and no speaker labels, so it cannot drive a pipeline whose whole value is
utterance timings and speaker attribution. The guardrails and the three check types are also ours to
interpret rather than a fixed spec. Decision, in three parts:
- `handout/transcript.pdf` is source material for writing our own call script, not pipeline input. We read
  it to learn the real script content and how agents actually talk, then write a script from it.
- We record that script ourselves: solo, one voice performing both parts, in a single continuous take.
  Agent lines and customer lines are read in a clearly different tone and pace, with a 1 to 2 second pause
  between every speaker turn, so nova-3 can split the turns cleanly.
- Because this is one microphone on one track, we send `diarize=true` and not `multichannel`. This
  supersedes D3's channel-first ordering: diarization is now the primary path, and multichannel becomes the
  fallback if a second voice or a stereo source becomes available later.
Consequence: D13's real-recording privacy concern no longer applies, since there is no real customer in
our audio. The recording is fully ours to use, commit and publish. The pipeline is unchanged in shape: it
still ingests audio, transcribes with speakers and timings, and scores against the library. The risk moves
from privacy to diarization quality, which the deliberate pauses and tone contrast are there to manage.

## D18. Speakers come from script alignment when diarization finds one voice
Context: the demo call is one person reading both roles (D17). Deepgram nova-3 returned speaker 0 for all
70 utterances, so every turn was labelled agent and talk ratio read 100%. Worse, it merged speaker changes
into single utterances: the recording disclaimer and the customer's "Yeah, that's fine" arrived as one row.
The first plan was to split turns on word-level silence, but the data ruled that out. The largest gap
between any two words in the whole call is 0.39s, and at several real speaker boundaries it is 0.00s. No
threshold separates turns, because the 1 to 2 second pauses that were recorded are not in the word timings.
Decision:
- Diarization stays the first choice. If Deepgram returns two or more speakers its labels are used and the
  script is never consulted.
- When it returns one speaker, turns are recovered by aligning the word stream against the ordered
  AGENT/CUSTOMER lines of the script that was actually read, `data/scripts/recorded_script.md`. The
  alignment is monotonic: it walks forward through the script and never revisits a line, so a repeated
  phrase cannot pull attribution backwards. Word timings give each recovered turn an exact start and end.
- Matching uses rapidfuzz `ratio` as the backbone, with `partial_ratio` and `token_set_ratio` damped by how
  much of the line the run covers. Undamped, both score 100 on a single word inside a long line and the
  aligner cuts a turn after one word.
- Below a match score of 70 (`SPEAKER_MATCH_MIN_SCORE`) the speaker is `unknown` and the turn's confidence
  is capped at 0.5, so a critical check that leans on it routes to REVIEW and never PASSes (hard rule 7).
- Every utterance stores `speaker_source`, either `diarization` or `script_alignment`, and the UI shows it
  so a reviewer knows how the speaker was decided.
- Word gaps are kept only as a tie-breaker between two near-equal candidate lines.
- A redaction token forces a turn boundary. The token joins the text before it as one turn labelled
  customer, since card data is spoken by the customer, and the words after it are re-aligned from that
  point. Without this the customer's card offer, the redacted digits and the agent's refusal fuse into one
  agent turn, which reads in the UI as the agent reciting a card number.
Consequence: this is a demo-only adapter for a single-voice recording, not a production mechanism. In
production the dialler supplies dual-channel audio, one party per channel, and speakers come from the
channel, which is the real fix. It is honest to show because we own the script being aligned against.
Measured on the demo call: 8 of 9 check-bearing lines attributed correctly before the redaction-token rule,
talk ratio 87.2% agent to 12.8% customer, and turn boundaries land within a word or two of the true change,
which the windowed Type A matching absorbs.
Added after the first commit: the redaction-token boundary rule is live and the demo call now scores 9 of 9,
with talk ratio 82.2% agent to 17.8% customer. The card turn is bounded to the 12 words before the token
(`CARD_LEAD_IN_WORDS`); an unbounded cut reached back to the start of the call and collapsed all 4.5 minutes
into one customer turn. After a forced cut the script pointer resyncs by searching the rest of the script,
still forward only, because a card turn can span several script lines and the token itself matches none.

## D19. The checklist is derived from the CIMET transcript, because no library export was provided
Context: `handout/` contains `transcript.pdf` and nothing else. There is no check-library export, no lead
dataset and no sandbox payload. The spike's six checks cannot stand in: they are energy checks (DMO, cents
per kWh, peak and off-peak tariffs) and this call sells NBN broadband, so every threshold and extractor in
them is for the wrong domain. Decision: build the retailer checklist from what the real agent actually says
in `handout/transcript.pdf`. Type A approved text is quoted from the transcript, cleaned only of
transcription artefacts (run-together words, the agent's filler "K?"). Type B checks are taken from the
data points the real call handles, corrected to the internet domain: monthly promo and ongoing price,
promo term, download speed, modem model, email, date of birth, service address. Type C is dead air,
interruptions and talk ratio, none of them critical, none of them blocking. The library lives as tracked
JSON in `app/checks/library/`, not in `data/`, which is gitignored. Two versions ship: v1 effective
2026-01-01 to 2026-09-30 and v2 from 2026-10-01 with a reworded disclaimer, which exists only to prove the
scorer resolves by call date (hard rule 8). The 2026-09-19 demo call resolves to v1, tested on both sides
of the boundary.
Consequence and findings, all of which are demo material rather than problems to hide:
- The source call fails its own disclaimer ordering rule. The agent confirms the service address twice
  before saying "please be advised that this call will be recorded". The rule is written as the control
  should be, so the real call FAILS it. This is the clearest illustration of why the ordering rule exists.
- The source call contains no explicit consent to switch. There is no "do you understand and agree"
  anywhere in it; the customer consents by ticking boxes in a web form. `consent_to_switch` is therefore
  marked `derived: true` with a source note, since its approved text is the control the absence implies
  rather than a quote. It is the only Type A check here not taken verbatim from the handout.
- No card data appears in the source. The agent muted the recording before payment, which is the compliant
  behaviour our own script mirrors with the agent's refusal line.
- Scored against v1, the self-recorded call gives: recording_disclaimer PASS 89.6,
  agent_and_company_identification PASS 92.1, consent_to_switch PASS 100.0,
  account_holder_confirmation REVIEW 86.2, plan_key_information FAIL 62.2,
  total_minimum_cost_disclosed FAIL 58.5. The three non-passes are paraphrase gaps between the recording
  and the real agent's wording, not engine faults. Thresholds were not lowered and the approved text was
  not rewritten to match the recording, because a checklist tuned until the demo passes measures nothing.
  Two critical checks failing on wording is a truthful result and a better demo than a clean sheet.
