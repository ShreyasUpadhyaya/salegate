---
name: qa-check-engine
description: Use when writing or changing any check evaluator, normaliser, extractor, threshold, gate rule or scoring test for the CIMET sales-call QA gate. Covers Type A verbatim/script checks, Type B factual matches, Type C behaviour notes, confidence routing and the evidence contract.
---

# QA check engine

## Inputs
- `CheckDefinition`: check_id, version, type (A/B/C), critical, weight, fatal, text or field refs, params.
- `Transcript`: ordered utterances with idx, speaker (agent/customer/unknown), start_s, end_s, text_redacted, avg_confidence, optional words.
- `Lead`: crm_fields, plan_code, rate card values, call_started_at.

## Output: CheckResult
status in PASS | FAIL | REVIEW | NOTE | NA, confidence 0 to 1, method, one-sentence reason, evidence list.
Reason format: what was expected, what was heard, where. Example:
`Agent quoted peak rate 28.6c at 14:02. Plan on the lead is 31.9c/kWh. Mismatch.`

## Normalisation (app/checks/normalise.py)
- Lowercase, strip punctuation, collapse whitespace, expand contractions, map number words to digits when smart_format missed them.
- Spoken email: "dot" -> ".", "at" / "at the rate" -> "@", "underscore", "dash"/"hyphen", spelled letters "j s m i t h" -> "jsmith", "double t" -> "tt".
- Money/rates: "twenty eight point six cents" -> 28.6; "cents per kilowatt hour", "c/kWh", "cents a unit" all mean c/kWh.
- Dates: "fifth of March ninety two", "05/03/1992" -> ISO. Australian day-first order.
- NMI is 10 or 11 alphanumerics, MIRN is 10 or 11 digits; spoken digit groups get joined.

## Type A: verbatim/script
1. Candidate spans: agent utterances only (fall back to all speakers if speaker is unknown, and lower confidence by 0.1).
2. Slide a window of 1 to 4 consecutive utterances. Score = max of rapidfuzz `partial_ratio` and `token_set_ratio` vs the approved text.
3. Thresholds from config: >= 88 PASS, 72 to 88 REVIEW, < 72 FAIL.
4. Long scripts (DMO/VDO, T&Cs): split the approved text into sentences, score each, require coverage >= 90% of sentences at >= 80. Report missing sentences in the reason.
5. Ordering rules: consent disclaimer must start before the first customer data capture utterance. If it comes later, FAIL with both timestamps.
6. Confidence: if avg word confidence of the matched span < 0.75, PASS or FAIL becomes REVIEW.
7. Semantic checks (account holder confirmed, customer agreed): regex/keyword first ("are you the account holder", customer "yes" within the next 2 utterances). Unresolved -> LLM adjudicator -> still unresolved -> REVIEW.

## Type B: factual
- Extract all candidate values with their utterance ids, then compare to CRM and rate card.
- Rates: find numbers near tariff words (peak, off-peak, shoulder, supply, daily supply, controlled load) within 8 tokens. Tolerance 0.05c. If quoted x 1.1 or / 1.1 matches the plan, it is a GST basis question: REVIEW, not FAIL.
- Email: compare normalised transcript email with CRM email. Exact -> PASS. Edit distance 1 to 2 with high confidence -> FAIL with both values (this is the lead 3613790 case). Low confidence -> REVIEW.
- Only the last read-back counts when the agent corrects themselves. Prefer agent read-back followed by customer confirmation.
- Value never mentioned on a critical check -> FAIL "not confirmed on the call", unless the check says optional.

## Type C: behaviour (never blocks)
- Dead air: gap between consecutive speech > 20 s. Evidence is the utterance before the gap.
- Interruptions: overlap > 1 s where the second speaker starts before the first ends.
- Talk ratio: agent seconds / total seconds. Note only when > 0.8.
- All are status NOTE with a coaching sentence.

## Gate (app/scoring/gate.py)
Any critical FAIL -> HELD_TL. Else any critical REVIEW -> QA_REVIEW. Else AUTO_SUBMIT with deterministic 5% QA sample.
Score with fatal: 0 if any fatal FAIL, else weighted. Score without fatal: weighted ignoring fatal flags. Compute both.

## Messy-call tests (must exist)
- Crosstalk: two speakers overlapping on the disclaimer -> not FAIL, REVIEW at worst.
- Mishear: "thirty one point nine" transcribed as "thirty one point nigh" -> REVIEW, not FAIL.
- Silence: 60 s gap -> NOTE only, gate unaffected.
- Card number spoken -> redacted token present, violation flag set, no digits anywhere in DB.
- Unscored lead -> submit returns 409.
- Every PASS has non-empty evidence (property test over all fixtures).
