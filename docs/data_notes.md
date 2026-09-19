# Data notes: CIMET handout files

Status: **transcript received and read, everything else still missing.** `handout/transcript.pdf` is a
6 page redacted transcript of one outbound sales call. No audio, no lead dataset, no check-library export
and no sandbox payload have been provided. Section 9 below records what the transcript actually contains.

Rule: when further files arrive, re-inspect and replace every section marked TO FILL with what the files
actually contain. Do not let an assumption here survive contact with a real file.

## 1. File inventory

| Expected file | Found | Format | Size | Notes |
|---|---|---|---|---|
| Call recording | **no, and none is coming** | n/a | n/a | CIMET provided no audio. We record our own, see D17 |
| Redacted call transcript | **yes** | pdf, 6 pages | 21 KB | `handout/transcript.pdf`, read in full, see section 9 |
| Synthetic lead dataset | not yet | expect csv or xlsx or json | | one row per lead, CRM fields |
| Check-library export | not yet | expect csv or xlsx or json | | the retailer checklist, versioned |
| Scoring sandbox payload | not yet | expect json | | the shape the sandbox expects back |

Extract the transcript text with:

```powershell
uv run --with pypdf python -c "from pypdf import PdfReader; print('\n'.join(p.extract_text() for p in PdfReader('handout/transcript.pdf').pages))"
```

For tabular files, print headers and the first three rows before anything else. For json, print the top
level keys and one full record.

## 2. Formats and fields

TO FILL. For each file record: exact column or key names, data types, null behaviour, date formats
(especially whether dates are ISO or Australian day-first, which matters for version resolution by call
date), and units on any rate column (cents per kWh vs dollars, GST inclusive vs exclusive).

Specific things to look for and write down:
- Lead dataset: the lead id column name, retailer identifier, agent id, TL id, site, campaign,
  `call_started_at` or equivalent, plan code, and every CRM field a Type B check compares against
  (email, DOB, address, NMI or MIRN, move-in date, concession, life support).
- Rate card: whether plan rates live in the lead dataset, a separate plan table, or the check library.
  Type B rate comparison needs a per-plan peak, off-peak, shoulder and supply charge.
- Whether the lead dataset says GST inclusive or exclusive anywhere. If it is silent, that ambiguity
  routes to REVIEW rather than FAIL, per PLAN.md.

## 3. Check-library export to our CheckDefinition model

TO FILL with the real column names. The target model, from the spike and PLAN.md, is:

| Our field | Type | Meaning | Likely source in the export |
|---|---|---|---|
| `check_id` | str | stable identifier, e.g. `recording_disclaimer` | a code or id column, else slugify the label |
| `version` | int | which revision of this check | a version column, else derive from effective dates |
| `retailer` | str | which retailer's checklist | a retailer column |
| `type` | A / B / C | verbatim-script, factual, behaviour | TO MAP, see below |
| `critical` | bool | a failure blocks the sale | a criticality or severity column |
| `weight` | float | contribution to the numeric score | a weight or points column |
| `fatal` | bool | failure zeroes the score outright | often folded into severity |
| `definition` | JSON | script text for A, field name for B, thresholds for C | the script or expected-value column |
| `effective_from` / `effective_to` | date | version window | date columns, else assume open-ended |
| `content_hash` | str | snapshot identity | computed by us, not in the export |

The type A/B/C split is ours, not CIMET's. The export will almost certainly not have a `type` column, so
Phase 5 classifies each row on load:
- **Type A** if the row carries approved script text the agent must say (disclaimer, DMO, account holder).
  Matched by rapidfuzz against agent utterances.
- **Type B** if the row names a CRM field or a value to verify (rate, email, DOB, address, NMI, move-in
  date, concession, life support, gift card). Extracted from the transcript and compared.
- **Type C** if the row is behavioural or coaching (dead air, interruptions, talk ratio, tone). Always a
  NOTE, never blocks.

Write the classification down explicitly as a mapping table in this file once the real rows are visible,
so it is auditable rather than buried in code. If a row resists classification, default it to Type A with
a REVIEW-biased threshold and flag it in the gaps list, never silently drop it.

`critical` and `fatal` are separate. Critical means a FAIL holds the sale for the TL. Fatal means the
numeric score goes to zero as well. Both may be encoded in one severity column in the export; if so,
record the exact mapping from severity value to our two booleans here.

Version resolution: the scorer picks the row where `effective_from <= call_started_at < effective_to`,
per hard rule 8 and D6. If the export has no effective dates, treat every row as effective from the
earliest call date in the lead dataset with no end, and note that as an assumption below.

## 4. What the scoring sandbox payload expects

TO FILL. Capture verbatim: the exact JSON schema, required vs optional keys, the enum of allowed status
values, whether it wants per-check rows or a single aggregate score, whether evidence is a required field
and in what shape, and how it identifies a check (our `check_id` or theirs).

This matters more than it looks. If the sandbox expects a different status vocabulary than our
PASS / FAIL / REVIEW / NOTE / NA, the mapping belongs here and in one adapter module, not scattered
through the scorer. Our internal contract stays as PLAN.md defines it.

## 5. Transcripts: timestamps and speakers

Resolved. The handout transcript has **no timestamps, no word timings and no confidence scores**. It has
speaker labels, but only as `Speaker 1` and `Speaker 2`, and the diarization in the source is poor: long
turns repeatedly contain both parties' speech run together (see section 9). It therefore cannot support
the click-to-play evidence contract or any Type C timing check.

Consequence, per D17: the handout transcript is source material for writing our own script, not pipeline
input. We record our own call and transcribe it with Deepgram `diarize=true`, single channel, which is
where real utterance ids, speakers, start_s, end_s and confidence come from.

## 6. Gaps and assumptions

Current:

0. **The domain is internet/NBN, not energy.** Confirmed by the transcript, see section 9. PLAN.md, the
   spike and this document were all written assuming an energy sale. Cents per kWh, peak/off-peak/shoulder,
   NMI/MIRN, DMO and the 0.05c rate tolerance do not apply. The equivalents are monthly dollar prices, a
   promo period, download and upload speeds, and a total minimum cost. **The check-engine mechanics carry
   over unchanged; only the extractors and script text change.** Items 6 and 7 below are superseded by this.
1. **Only the transcript arrived.** No lead dataset, no check-library export, no sandbox payload. Phase 5
   onward still depends on these. If they never arrive, the D15 fallback applies: seed the library from
   our own checks against a synthetic lead, now written for internet rather than energy.
2. **Assumed one retailer.** PLAN.md scopes to the retailer in the check-library export. If the export
   carries several, we pick the one with the most complete checklist and say so in the README.
3. **Assumed the check library has no `type` column.** We classify A/B/C on load. If CIMET supplies a
   type, drop our classifier and use theirs.
4. **Assumed effective dates may be missing.** If so, all checks are treated as currently effective and
   the version-by-call-date demo runs against a synthetic second version we create in the library table,
   labelled as such. The mechanism is still real, the second version is illustrative.
5. **Our own recording is one call, one lead.** It attaches to a synthetic lead and the join is ours by
   construction, so nothing is manufactured or needs explaining away.
6. Superseded by item 0. Prices are monthly dollars, not cents per kWh. Tolerance becomes exact-cents
   matching on a dollar amount, which is stricter and simpler than the 0.05c band.
7. Superseded by item 0. No GST ambiguity appeared in the transcript; advertised internet pricing is
   inclusive. If a later file says otherwise, the REVIEW-not-FAIL rule still stands.
8. **No card number is spoken in the source call.** The agent muted the recording and the customer typed
   card details into a web form, which the redaction notes confirm. Hard rule 4 holds regardless, and our
   own script deliberately speaks a fake test card number so the Luhn pass and the PCI flag are exercised
   on real audio rather than only in a unit test.
9. **The real call fails the consent-ordering rule.** Its disclaimer comes after address confirmation.
   Our script puts it first, and the failing order is covered by a test fixture instead. Worth saying out
   loud in the demo: the gate catches this exact pattern.

## 7. Carried forward from the rehearsal spike

Settled before build day against CIMET's worked example (Lead 3613790, Retailer 1), do not re-derive:

- rapidfuzz thresholds: 88 and above PASS, 72 to 88 REVIEW, below 72 FAIL.
- Rate extractor: regex near tariff words, tolerance 0.05c. Caught 28.6c quoted vs 31.9c plan.
- Gate holds for TL on any critical FAIL and lists which checks failed.
- Every PASS carries non-empty evidence. This is a test, not a convention.
- Evidence timestamps are tested, not only status. Window ties break to the shortest window.

Two fixed bugs to carry forward, per D14:

1. Every Type B extractor isolates its span with a targeted regex **before** normalising. Never
   find-and-replace across a whole utterance. See `reference/spike/normalise.py` `_EMAIL_SPAN`.
2. Type C timing fixtures must be continuous back-to-back utterances. Highlight-only fixtures invent
   fake dead air.

## 8. Privacy handling for this data

Per hard rule 2 and D17. Two separate things, do not conflate them:

- **The handout transcript** is CIMET's, is marked CONFIDENTIAL, and carries a stated residual
  re-identification risk even after redaction. `handout/` is gitignored and stays that way. Do not quote
  its lines verbatim into committed files. The script we derive from it is paraphrased and uses our own
  invented test values.
- **Our own recording** has no real customer in it, so it is ours to commit or publish. The audio and full
  transcript stay gitignored anyway (hard rule 2), because the pipeline should be habitually safe.

Anything written into `results/` or a commit quotes the check outcome, not a real email, phone, DOB or
address. Aggregate numbers are not PII and commit freely.

## 9. What the handout transcript actually contains

Read in full on build day. One outbound call, roughly 15 to 20 minutes of talk judging by content.

**This is an internet/NBN sale, not energy.** The spike and PLAN.md assume an energy sale (cents per kWh,
NMI/MIRN, peak/off-peak, DMO). None of that appears. The real call sells an NBN plan with monthly dollar
pricing. Every Type B extractor and Type A script check has to be rebuilt around this domain. This is the
single biggest change the handout forces, recorded as a gap in section 6.

Identifiers are replaced with placeholder tags: `[CUSTOMER_NAME]`, `[CUSTOMER_FULL_NAME]`, `[AGENT_NAME]`,
`[SERVICE_ADDRESS]`, `[DELIVERY_ADDRESS]`, `[EMAIL]`, `[PHONE]`, `[DOB]`, `[ACCOUNT_NUMBER]`,
`[OTP_CODE]`, `[REFERENCE_NUMBER]`, `[PROVIDER_A]`. The values behind them are not visible to us, which
means the handout cannot supply CRM comparison values. Our own script invents them.

### Section order of the call

1. Greeting, agent names themselves and the comparison service.
2. Reason for call: customer is looking for better internet plans.
3. Address confirmation, read back to the customer.
4. **Recording disclaimer**, delivered after the address was already confirmed.
5. Address re-check, NBN technology type stated (fibre to the premises).
6. Discovery: current provider, current price, current speed, household size, usage type, landline need.
7. Offer: promotional price, promo duration, then the ongoing price.
8. Objection handling: customer nearly declines over small savings, agent adds a free modem.
9. Modem questions: brand new vs refurbished, keeping it on switch, delivery cost and time.
10. **Full plan read-out**: contract term, download and upload speeds, peak window, both prices, modem
    model, compatibility, total minimum cost.
11. Identity capture: title, first and last name as per ID, email, mobile, date of birth.
12. Previous provider's bill: account number, agent hunts for an "ABC ID" that is not on the bill.
13. Connection address and timing, modem delivery address (differs from service address).
14. Payment method preamble, then **the agent mutes the recording** for card capture.
15. Guided web-form completion: email link, plan select, modem select, address entry struggle.
16. Total minimum cost discrepancy: form shows a higher figure, agent reassures it will not be charged.
17. OTP from SMS, application submitted, reference number read back.
18. Cross-sell attempt: electricity and gas. Customer declines, supply is embedded in their complex.
19. Close: congratulations, contact details, sign-off.

### Type A script checks, with example agent lines

Quoted short and paraphrased where possible, per section 8.

| Check | Example agent line in the call | Notes for our script |
|---|---|---|
| Recording disclaimer | "please be advised that this call will be recorded for quality assurance and, training purposes" | **Arrives late**, after the address was confirmed. See the ordering finding below |
| Account holder confirmation | "this will be under your name. Am I correct?" then "can you please verify your first and last name as per ID" | Two-part: account holder, then ID verification |
| Plan read-out | "the original plan cost is seventy two dollars and ninety per month, but we have an offer ongoing where you will get this plan as forty two dollars and ninety only per month for the first six months" | Stands in for the energy DMO read. Promo price, promo term, ongoing price |
| Contract term | "comes with a one to one contract only" garbled; elsewhere "it's just a month to month contract" | Two inconsistent statements, good REVIEW candidate |
| Speed disclosure | "twenty five Mbps typical in download speed and eight point five Mbps typical in the upload speed from seven PM to eleven PM" | Typical evening speed, a real compliance line |
| Total minimum cost | "the total minimum cost will be forty two dollars and ninety only. No setup fee." | Contradicted later by the form's 317 dollars |
| Modem cost and ownership | "it's hundred percent free... Even you switch provider, even you move to a different property, you can keep and use the same modem" | Repeated four times in the call |
| Close and identification | "This is [AGENT_NAME] again from Econnex Comparison" | Agent identifies employer at open and close |

**Ordering finding, directly relevant to hard rule 11.** The disclaimer is spoken *after* the agent has
already stated and confirmed the customer's service address. If consent must precede data collection, this
real call would fail that ordering check. That makes it a good basis for our deliberate test: our script
places the disclaimer correctly, and the ordering rule is proven by a unit test fixture instead.

### Type B factual data points present

| Data point | Value in the call | Comparable against |
|---|---|---|
| Promo price | 42.90 per month | plan rate card |
| Ongoing price | 72.90 per month | plan rate card |
| Promo duration | 6 months | plan rate card |
| Download speed | 25 Mbps typical | plan rate card |
| Upload speed | 8.5 Mbps typical | plan rate card |
| Peak window | 7pm to 11pm | plan rate card |
| Total minimum cost | 42.90 stated by agent, 317 shown on the form | plan rate card, and internally inconsistent |
| New development fee | 275, stated as not applicable | plan rate card |
| Modem model | Netcomm CF40 Wi-Fi 6 (transcribed variously as "Netcom CF forty", "Netcom p s forty") | plan rate card |
| Modem cost | 0 upfront | plan rate card |
| Current provider | iPrimus | CRM field |
| Current price | 65 per month | CRM field, discovery capture |
| Current speed | 25 Mbps | CRM field, discovery capture |
| Email | `[EMAIL]`, verified by read-back | CRM field |
| Mobile | `[PHONE]`, verified by read-back | CRM field |
| Date of birth | `[DOB]`, verified by read-back | CRM field |
| Service address | `[SERVICE_ADDRESS]` | CRM field |
| Delivery address | `[DELIVERY_ADDRESS]`, deliberately different | CRM field |
| Previous account number | `[ACCOUNT_NUMBER]` | CRM field |
| Reference number | `[REFERENCE_NUMBER]`, read back by customer | CRM field |
| NBN technology | fibre to the premises | CRM field |
| Connection timing | as soon as possible | CRM field |

The modem model is a useful extractor target precisely because STT mangles it three different ways. That
is a realistic fuzzy-match problem rather than an invented one.

### Behavioural cues visible in the text

Timings are absent, so these are inferred from wording and are only indicative until we record our own
call:

- **Heavy interruption and overlap.** Speaker turns repeatedly contain both parties, e.g. a single
  Speaker 2 turn containing "Do you have one?IPRIMUS.You are currently with iPRIMUS." The customer's
  answer is swallowed into the agent's turn. This is what poor diarization looks like and is the strongest
  argument for the deliberate pauses in our own recording.
- **Likely dead air** during the bill hunt ("Hang on", the ABC ID search) and during the web form address
  struggle, where the customer is typing and re-entering an address repeatedly.
- **Agent talk ratio is high**, particularly in the plan read-out, which is one long uninterrupted block.
- **Repetition as a filler**, "K?" ends a large proportion of agent turns.
- **Customer confusion signals**: "Sorry. I didn't get that", "And my what, sir?", and an address that
  fails validation several times.
- **The recording mute** is stated explicitly: "before that, I need to mute the recording" then "The
  recording is already resumed." No card details appear anywhere in the transcript, which the redaction
  notes confirm. Our PCI check still runs per hard rule 4, and our script includes a spoken fake card
  number so the Luhn pass has something to catch.
