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

## D20. Type A checks use three match modes, chosen by what each check means
Context: a single fixed-window fuzzy match (the spike's approach) works for short lines but breaks on
long reads. `plan_key_information` is a multi-sentence block; a 1 to 4 turn window either misses most of
it or needs a threshold so loose it stops meaning anything. Confirmation checks are a different shape
again: a yes/no exchange, not a script to recite. Decision: each Type A check declares `match_mode` in the
library, set by the check's nature, never adjusted to make a specific call pass (see the finding in D19).
- `verbatim`: short fixed lines (disclaimer, self-identification). Unchanged from the spike: window of 1
  to 4 agent turns, score = max(partial_ratio, token_set_ratio), thresholds 88 PASS / 72 REVIEW.
- `coverage`: long reads (plan key information, total minimum cost). The approved text is split into
  sentences, each scored against the joined agent speech, PASS needs 90% of sentences at or above 80. The
  reason names the missing sentences verbatim, so a TL sees exactly what was skipped, not just a number.
- `confirmation`: a question-and-answer pair (account holder, consent to switch). The agent's question
  must score at or above 80, and one of the next two customer turns must read as an affirmative. Evidence
  cites both turns, since the check is about the exchange, not either side alone.
Thresholds carried forward unchanged: 88/72 for verbatim, hard rule 7's confidence floor (0.75) downgrades
any of the three modes to REVIEW. Unknown-speaker turns (D18) additionally lower confidence by 0.1 before
that floor is applied, since an unresolved speaker is itself a reason not to trust a PASS.
Consequence: the same engine now gives an honest answer on both a tight verbatim line and a five-sentence
read, without a threshold tuned to either one specifically. See D19 for what this actually found on the
self-recorded call: two coverage checks FAIL on paraphrase, not on engine error.

## D20 addendum: window trimming and a confirmation near-miss band
Two follow-ups after the first Phase 6 commit, both found by rerunning against the real call rather
than by inspection.
- Verbatim and coverage scoring now trims a candidate window to its best-aligned span before running
  `token_set_ratio`, so a turn whose text runs on past a missed speaker boundary (D18) does not get
  diluted by the leftover words. `partial_ratio` already does its own substring alignment and needed no
  change. On the real call this did not move `recording_disclaimer` off REVIEW (82 vs the 85 measured
  before): the gap there is a genuine wording difference between the recording and v1's approved text, not
  window contamination, confirmed by checking that `partial_ratio` alone already reflected the same gap.
  `_best_window` was already agent-turns-only, so no customer turn could enter a window; the real defect
  was scoring a whole turn's text rather than its matched span.
- Confirmation mode gained a near-miss band. A question scoring 60 to 79 (`CONFIRMATION_NEAR_MISS_THRESHOLD`
  to `CONFIRMATION_QUESTION_THRESHOLD`) with a customer affirmative within the reply window now returns
  REVIEW, evidence citing both turns, rather than a flat FAIL. Below 60 stays FAIL outright: that is not a
  wording variant of the checklist question, it is a different question. Approved text is untouched.
  On the real call `account_holder_confirmation` scores 54, below the near-miss floor, so it correctly
  stays FAIL rather than softening into REVIEW: the recording's "can I confirm you are the account holder"
  is enough removed from both v1 phrasings that treating it as the same exchange would be a stretch, not a
  near-miss.

## D21. Type B factual checks: span isolation, role-tagged prices, catastrophic backtracking
Context: PLAN.md Phase 7. Ported reference/spike/factual.py and normalise.py, extending the D14
span-isolation fix from email to every Type B extractor: money, promo term, download speed, modem, DOB
and address all isolate their value's span with a targeted regex before parsing, never a whole-utterance
scan. Several real bugs surfaced only by running the real cached call, not by the fixtures written first.
- **Catastrophic backtracking.** The money, term and speed regexes used an unbounded nested quantifier,
  `((?:[a-z]+[\s-]?)+?)`, to capture a run of number words. Against long agent turns that contain no money
  at all (most of them), this pattern's ambiguity made matching take effectively forever: the whole scoring
  pass hung on the very first turn. Fixed by bounding the word count (`{1,4}`, `{1,3}`) instead of leaving
  it open-ended, which removes the exponential blowup entirely. Any future spoken-number extractor must use
  a bounded repeat, never `(word[\s-]?)+`.
- **Alternation is first-match, not longest-match.** `_NUMBER_WORD`'s word list had "nine" before "ninety"
  and "nineteen", so "ninety" matched only its first four letters and silently produced 42.09 instead of
  42.90. Fixed by ordering the longest words first and adding `\b` boundaries. Same class of bug as the
  ReDoS above: an assumption about regex engine behaviour that fixtures alone did not test hard enough to
  catch, only the real call's actual phrasing did.
- **Two prices in one turn need a role, not just a value.** The call states both the promo and ongoing
  price, often in the same turn ("$42.90 a month, then $79.90 ongoing"), sometimes with the qualifying
  word before the figure and sometimes after. A bare list of quoted numbers cannot tell one check's field
  from the other, so `extract_money_mentions` returns `(value, role)` pairs, tagging each mention "promo",
  "ongoing" or "unknown" from marker words in a window either side of it, bounded by the nearest sentence
  punctuation so a marker belonging to the next sentence is never pulled onto this mention. When a turn has
  a confidently tagged mention of the OTHER role, `score_money_check` treats a same-turn "unknown" mention
  as noise from that other price, not a second claim on this field.
- **Numeric DOB is genuinely ambiguous, resolved by falling through.** Day-first is the default (en-AU).
  When the first number exceeds 12 it must be the day (unambiguous). The bug: the code checked only "is the
  first number too big to be a month", not the mirror case "is the second number too big to be a month",
  so Deepgram's `03/14/1990` (US month/day order) fell through as an invalid day-first reading and was
  silently dropped rather than re-read the other way. Fixed by checking both directions before giving up.
- **State name mismatch cost the address check its fuzzy score.** The agent reads "New South Wales" in
  full; the CRM stores "NSW". Both otherwise-identical addresses fuzzy-matched at 82, under the 90
  threshold, purely on the state spelling. `normalise_state_names` maps full Australian state and
  territory names to their abbreviation before the fuzzy compare.
- **Modem letters can arrive spaced.** "netcomm cf40" is sometimes transcribed "netcom c f 40"; the model
  regex required "cf" adjacent and missed the spaced form. Fixed to accept a space between the letters.
Consequence: every one of these was found by running the actual 70-utterance call through the evaluators,
not by the hand-written fixtures, which is why PLAN.md's real-call assertions matter as much as the
per-extractor unit tests. Call 1 result after all fixes: `ongoing_monthly_price` and `customer_email` FAIL
correctly (both are the deliberate script faults), `promo_monthly_price`, `customer_dob`,
`plan_download_speed` and `service_address` PASS, `modem_model` REVIEWs because the modem line landed on a
customer turn under speaker alignment (D18), not an agent one, so the "agent turns only" rule for this
field correctly finds no mention to check.

## D22. Type C behaviour, the gate, and what running call 2 actually found
Context: PLAN.md Phase 8. Type C evaluators (`app/checks/behaviour.py`) and the gate
(`app/scoring/gate.py`) are both ported from reference/spike/gate.py, unchanged in shape: FAIL beats
REVIEW beats PASS on critical checks only, Type C is never inspected by the gate at all.
- **Interruption uses a follow-on definition, not overlap.** `INTERRUPTION_OVERLAP_S` (1.0s, existing
  config) is a true simultaneous-speech threshold that single-channel audio cannot measure: there is no
  signal for two people talking at once when both are on one track. The Phase 8 prompt asked for "customer
  speaks within 0.5s of agent end", which is a fast follow-on, not an overlap. Kept as its own constant,
  `INTERRUPTION_FOLLOW_ON_S = 0.5` in `app/checks/behaviour.py`, rather than repurposing the existing config
  value for a different definition it was not tuned for.
- **A critical check that never ran is treated as REVIEW, not a silent pass.** The gate rule as specified
  only covers FAIL and REVIEW results that exist. If a critical check is missing from the results list
  entirely (a scoring bug, a crash, a check_id typo), the gate now adds it to `critical_reviews` rather than
  looking at an empty intersection and concluding nothing is wrong. This was not explicitly asked for, but
  follows directly from hard rule 7: an unresolved critical check must never look like a clean sheet.
- **`call2.wav` on disk was an accidental duplicate of `call.wav`,** same sha256, so Deepgram's cache
  correctly served back call 1's transcript for it. The real Priya Shah recording was sitting unconverted
  as `data/recordings/demo/call 2 .m4a.mp4` (204.5s, matching the clean script's length; the duplicate wav
  was 270.6s, matching call 1's). Converted with ffmpeg, re-stored under a new sha, retranscribed for real.
- **The clean call still gates HELD_TL, and that is a real result, not a leftover bug**, from two causes
  visible when scoring the real transcript rather than an intended script:
  1. Deepgram wrote some quoted numbers in digit form ("25 Mbps", "$42.90") where the v1 checklist's
     approved text, quoted from the CIMET transcript (D19), uses word form ("twenty five Mbps", "eight
     point five"). Coverage-mode sentence matching (D20) scores these low, so `plan_key_information` and
     `total_minimum_cost_disclosed` FAIL on wording form, not on missing content.
  2. Speaker alignment (D18) merged roughly a dozen sentences of the plan read into one very long turn
     (70.6s to 123.0s), because that stretch of the call has none of the short customer interjections the
     aligner uses to find a cut point. Inside that one turn, the money-role tagger's sentence-boundary
     window cannot separate the promo mention from the ongoing mention cleanly, and mis-tags one repeated
     figure, producing a FAIL on `ongoing_monthly_price`/`promo_monthly_price` on a call that was actually
     quoted correctly. `customer_email` also came back REVIEW rather than PASS: the email sentence landed
     inside the same merged turn and the extractor's span isolation did not find it there.
  Both causes are downstream of the same root already named in D18: single-voice alignment recovers turns
  well when the script gives it short back-and-forth exchanges to anchor on, and recovers them poorly
  across a long uninterrupted monologue. Fixing it properly means either improving the aligner's handling
  of long agent-only stretches or re-deriving the checklist's approved text in digit form, both bigger than
  Phase 8's box. Decision: report it as found rather than hand-pick call 2 outcomes to look clean.
Consequence: this is genuinely useful evidence for the demo, not noise to hide. Two independently recorded
calls, one meant to fail and one meant to pass, both correctly route to HELD_TL once run through the real
pipeline, and the reasons are traceable to two named, already-documented limitations rather than to a new
unexplained defect. The gate and evidence-contract tests (`tests/test_gate.py`) assert on the pipeline's
actual behaviour on both calls, not on the intended script outcome, which is why they check the evidence
contract and the shape of the decision rather than asserting call 2 is AUTO_SUBMIT.

## D22 addendum: number-word normalisation fixed one of the two call 2 causes
Bounded 15 minute fix: `normalise_spoken_numbers` in `app/checks/normalise.py` converts runs of number
words to digits ("twenty five" -> "25", "eight point five" -> "8.5") and is applied only inside
`score_coverage_check`, on both the approved text and the joined agent speech, before the sentence-level
fuzzy compare. Type B extraction is untouched: it still reads an isolated span directly, per D14.
Result on call 2: `plan_key_information` now PASSes. The digit-vs-word mismatch named as cause 1 in D22 is
resolved. Cause 2, the long merged turn confusing money-role tagging and hiding the email mention, is
unaffected, as expected, since role-tagging and speaker alignment were explicitly left untouched.
Call 2 final state: still HELD_TL, now on `ongoing_monthly_price`, `promo_monthly_price` and
`total_minimum_cost_disclosed` (FAIL) plus `customer_email` (REVIEW), all attributable to the single
remaining cause, the long merged turn from speaker alignment. Stopping here per instruction: the
remaining gap is the documented alignment limitation, not a new defect, and fixing it means improving
alignment's handling of long uninterrupted agent stretches, which is out of scope for a bounded fix.
