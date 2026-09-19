"""Score a call and decide the gate. Ported from reference/spike/gate.py.

Runs every check in the retailer's checklist for the call's date (hard rule 8),
then applies the gate rule from PLAN.md: FAIL beats REVIEW beats PASS on
critical checks only. Type C never enters the decision, since it is coaching,
not a gate input (PLAN.md, hard rule: "Type C always NOTE, never blocks").

No DB access here by design, matching the evaluator contract in CLAUDE.md: this
module takes a snapshot, turns and a lead dict, and returns plain data. The
caller (a later phase's scoring/scorer.py) is responsible for persisting a
Score row and CheckResult rows from what this returns.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from app.checks.behaviour import score_type_c_check
from app.checks.factual import score_type_b_check
from app.checks.library import CheckLibrarySnapshot, resolve_for_date
from app.checks.models import CheckResultDict, TurnDict
from app.checks.verbatim import score_disclaimer_ordering, score_type_a_check
from app.config import get_settings

DECISION_HELD_TL = "HELD_TL"
DECISION_QA_REVIEW = "QA_REVIEW"
DECISION_AUTO_SUBMIT = "AUTO_SUBMIT"


def score_all_checks(
    snapshot: CheckLibrarySnapshot, turns: list[TurnDict], lead: dict[str, Any]
) -> list[CheckResultDict]:
    """Run every check in the snapshot against this call. One result each."""
    results: list[CheckResultDict] = []

    for check in snapshot.of_type("A"):
        result = score_type_a_check(check, turns)
        if check.check_id == "recording_disclaimer":
            result = score_disclaimer_ordering(check, turns, result)
        results.append(result)

    for check in snapshot.of_type("B"):
        results.append(score_type_b_check(check, turns, lead))

    for check in snapshot.of_type("C"):
        results.append(score_type_c_check(check, turns))

    return results


def is_sampled_for_qa(lead_id: str, sample_percent: int | None = None) -> bool:
    """Reproducible 5% sample: the same lead is always sampled or not (D10)."""
    if sample_percent is None:
        sample_percent = get_settings().qa_sample_percent
    bucket = int(hashlib.sha256(lead_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    return bucket < sample_percent


def decide_gate(
    results: list[CheckResultDict],
    snapshot: CheckLibrarySnapshot,
    lead_id: str,
) -> dict[str, Any]:
    """FAIL beats REVIEW beats PASS, on critical checks only.

    1. Any critical FAIL -> HELD_TL, name every failing check.
    2. Else any critical REVIEW -> QA_REVIEW, name every unresolved check.
    3. Else every critical check PASSed -> reproducible 5% sample to QA_REVIEW,
       the rest AUTO_SUBMIT.
    Type C results are never inspected here: they are NOTE by construction and
    the gate does not hold on them (PLAN.md).
    """
    critical_ids = snapshot.critical_ids
    by_id = {r["check_id"]: r for r in results}

    critical_fails = [
        r["check_id"] for r in results if r["check_id"] in critical_ids and r["status"] == "FAIL"
    ]
    critical_reviews = [
        r["check_id"] for r in results if r["check_id"] in critical_ids and r["status"] == "REVIEW"
    ]

    missing_critical = critical_ids - set(by_id)
    if missing_critical:
        # A critical check that never ran at all is not a clean bill; treat it
        # the same as a REVIEW so the gate never silently skips it.
        critical_reviews.extend(sorted(missing_critical))

    if critical_fails:
        decision = DECISION_HELD_TL
        sampled = False
    elif critical_reviews:
        decision = DECISION_QA_REVIEW
        sampled = False
    else:
        sampled = is_sampled_for_qa(lead_id)
        decision = DECISION_QA_REVIEW if sampled else DECISION_AUTO_SUBMIT

    return {
        "decision": decision,
        "sampled_for_qa": sampled,
        "critical_fails": sorted(critical_fails),
        "critical_reviews": sorted(critical_reviews),
    }


def score_and_gate(
    call_started_at: date | datetime,
    retailer: str,
    turns: list[TurnDict],
    lead: dict[str, Any],
) -> dict[str, Any]:
    """The whole Phase 8 pipeline: resolve the library, score, gate.

    Returns the snapshot used (for the library_snapshot_hash a later phase
    stores on the score row), every check's result, and the gate decision.
    """
    snapshot = resolve_for_date(call_started_at, retailer)
    results = score_all_checks(snapshot, turns, lead)
    gate = decide_gate(results, snapshot, lead["lead_id"])

    return {
        "snapshot_hash": snapshot.snapshot_hash,
        "library_version": snapshot.checks[0].version if snapshot.checks else None,
        "results": results,
        "gate": gate,
    }
