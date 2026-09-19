# Data notes: CIMET handout files

Status: **awaiting handout.** As of the Phase 0 inspection, `handout/` exists but is empty (zero files).
Nothing below describes a file that has actually been read. This document is written as the checklist to
fill in the moment the CIMET files land, plus the assumptions the build proceeds on until then.

Rule: when the files arrive, re-run Phase 0 inspection and replace every section marked TO FILL with what
the files actually contain. Do not let an assumption here survive contact with a real file.

## 1. File inventory

| Expected file | Found | Format | Size | Notes |
|---|---|---|---|---|
| Call recording | not yet | expect wav or mp3 | | ffprobe for duration, channels, sample rate |
| Synthetic lead dataset | not yet | expect csv or xlsx or json | | one row per lead, CRM fields |
| Check-library export | not yet | expect csv or xlsx or json | | the retailer checklist, versioned |
| Scoring sandbox payload | not yet | expect json | | the shape the sandbox expects back |
| Brief or handout PDF | not yet | pdf | | source of the Lead 3613790 worked example |

Inspection commands to run when the files arrive:

```powershell
Get-ChildItem -Recurse .\handout
ffprobe -v error -show_entries format=duration,bit_rate -show_entries stream=channels,sample_rate,codec_name -of default=noprint_wrappers=1 .\handout\<recording>
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

TO FILL once the handout is inspected. Two cases:

- **If the handout ships a transcript**, record whether it has per-utterance start and end times, speaker
  labels, word-level timings, and confidence. If it has no timestamps, it cannot support the click-to-play
  evidence contract or any Type C timing check, and we transcribe the audio ourselves regardless.
- **If the handout ships only audio**, we produce the transcript with Deepgram, per D2. The decision
  between `multichannel` and `diarize` is made by ffprobe channel count, per D3: two channels means
  multichannel, otherwise diarize and map speaker 0/1 to agent/customer by who reads the disclaimer.

Either way the evidence contract needs utterance id, speaker, start_s, end_s and redacted text. A
transcript without timings is a fallback for content checks only, and Type C is cut if we are on it.

## 6. Gaps and assumptions

Current, all of them driven by the empty handout:

1. **No handout files exist yet.** Everything about formats, column names and the sandbox schema is
   unverified. This is the single biggest open risk in the build, since Phase 5 onward depends on it.
2. **Assumed one retailer.** PLAN.md scopes to the retailer in the check-library export. If the export
   carries several, we pick the one with the most complete checklist and say so in the README.
3. **Assumed the check library has no `type` column.** We classify A/B/C on load. If CIMET supplies a
   type, drop our classifier and use theirs.
4. **Assumed effective dates may be missing.** If so, all checks are treated as currently effective and
   the version-by-call-date demo runs against a synthetic second version we create in the library table,
   labelled as such. The mechanism is still real, the second version is illustrative.
5. **Assumed the recording is a single call, one lead.** If it maps to a lead id in the dataset, use that
   lead. If not, we attach it to a synthetic lead and note the join is manufactured.
6. **Assumed rates are cents per kWh.** The spike used 28.6c vs 31.9c with a 0.05c tolerance. If the
   export uses dollars, the extractor needs a unit normalisation step before comparison.
7. **GST treatment is unknown.** Per PLAN.md, inclusive vs exclusive ambiguity is a REVIEW, not a FAIL.
8. **PCI redaction is unverified against the real audio.** We do not know yet whether a card number is
   even spoken in the recording. Hard rule 4 holds regardless: Deepgram `redact=pci` plus a local Luhn
   pass run on every transcript, spoken card or not.

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

Per hard rule 2 and D13. The recording and its full transcript are local-only and gitignored. Anything
written into `results/` or a commit quotes the check outcome, not the customer's real email, phone, DOB or
address. Masked (`j.smith@gm***`) or paraphrased ("email read-back differs from CRM by one character").
Aggregate numbers are not PII and commit freely. The backup video uses a synthetic lead only.
