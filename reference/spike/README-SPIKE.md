# Rehearsal spike, not the submission

Throwaway code to pressure-test the riskiest logic before build day, using the exact numbers from
CIMET's own worked example (Lead 3613790, Retailer 1). Do not copy this into tomorrow's repo verbatim;
rebuild it fresh there, in the phases PLAN.md lays out, with real git history starting at 09:30.
What to carry over is the understanding, not the files.

Run it: `python3 tests/test_spike.py` for a printed table, or `python3 -m pytest tests/ -q`.

## What it proved works
- Fuzzy verbatim matching (rapidfuzz) correctly passes the disclaimer, account-holder and DMO checks.
- Factual extraction correctly catches the rate mismatch (28.6c quoted vs 31.9c plan) with both values
  in the reason string, matching evidence.
- The gate correctly holds for TL when a critical check fails, and lists which checks failed.
- Every PASS carries non-empty evidence, checked as an invariant.

## Two real bugs this caught (details in normalise.py and factual.py comments)
1. **Spoken-email normalisation on the whole utterance, not just the email span.**
   "and your email is j dot smith at gmail dot com" got fully dot/at-replaced, producing
   "andyouremailisj.smith@gmail.com" instead of "j.smith@gmail.com". The fuzzy-similarity fallback
   masked this as a REVIEW instead of surfacing the real bug. Fixed by regex-matching just the
   `word at word dot word dot tld` span, ignoring the leading sentence.
   **Lesson for tomorrow:** every extractor needs a span-isolation step before normalising, not just
   a global find-and-replace on the full utterance text.
2. **Sparse test fixtures produce misleading dead-air data.** Using only the "highlight" utterances
   from the PDF (10 lines spanning a 30 minute call) creates artificial 100+ second gaps that don't
   reflect a real continuous transcript. Not a code bug, but a reminder: don't tune dead-air thresholds
   against a fixture built from highlights alone; use the real transcript once it exists.

## Files
models.py, normalise.py, verbatim.py, factual.py, gate.py, fixtures.py, tests/test_spike.py

## Third bug, caught in review
3. **Script evidence pointed at the wrong timestamp.** The verbatim matcher kept the first window that hit
   the top score. A 3-utterance window starting at the disclaimer also contained the account-holder line,
   so every script check claimed "matched at 12s". Tests passed because they only checked status.
   Fixed with a shortest-window tie-break, plus a new test asserting each check's evidence start time
   (12s, 161s, 595s). **Lesson for tomorrow:** test the evidence, not only the status. Traceability is 20% of the score.
