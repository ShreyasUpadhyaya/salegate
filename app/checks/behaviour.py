"""Type C evaluators: coaching notes from timing alone. Never block a sale.

Ported from reference/spike/gate.py's dead_air_notes per PLAN.md Phase 8.
Always NOTE, never PASS/FAIL/REVIEW: hard rule and PLAN.md agree these are
non-critical and must never hold a sale (see the gate in app/scoring/gate.py,
which never even looks at a Type C result's status).
"""

from __future__ import annotations

from typing import Any

from app.checks.library import CheckDefinition
from app.checks.models import CheckResultDict, TurnDict
from app.config import DEAD_AIR_THRESHOLD_S

# "Interruption" here means the customer starts speaking within this many
# seconds of the agent's turn ending: a fast follow-on or talk-over, not the
# true overlapping-speech definition INTERRUPTION_OVERLAP_S (1.0s) is tuned
# for. Kept as its own constant rather than reusing that one, since single
# channel audio has no simultaneous-speech signal to measure overlap from;
# this is the closest proxy timing alone can give. See DECISIONS D22.
INTERRUPTION_FOLLOW_ON_S = 0.5


def _evidence(turn: TurnDict) -> dict[str, Any]:
    return {
        "utterance_id": turn.get("idx"),
        "speaker": turn.get("speaker"),
        "start_s": turn.get("start_s"),
        "end_s": turn.get("end_s"),
        "text_redacted": turn.get("text_redacted", ""),
    }


def score_dead_air(check: CheckDefinition, turns: list[TurnDict]) -> CheckResultDict:
    """Every gap of DEAD_AIR_THRESHOLD_S or more between consecutive turns.

    One CheckResultDict per check_id, evidence lists every gap found (not just
    the first), so a long call with several silences shows all of them.
    """
    ordered = sorted(turns, key=lambda t: t.get("start_s", 0.0))
    evidence: list[dict[str, Any]] = []
    gap_descriptions: list[str] = []

    for previous, current in zip(ordered, ordered[1:], strict=False):
        gap = current.get("start_s", 0.0) - previous.get("end_s", 0.0)
        if gap >= DEAD_AIR_THRESHOLD_S:
            evidence.append(_evidence(previous))
            evidence.append(_evidence(current))
            gap_descriptions.append(f"{gap:.1f}s at {previous.get('end_s', 0.0):.1f}s")

    if gap_descriptions:
        reason = f"{check.title}: {', '.join(gap_descriptions)}."
    else:
        reason = f"{check.title}: no gap reached the {DEAD_AIR_THRESHOLD_S:.0f}s threshold."

    return CheckResultDict(
        check_id=check.check_id,
        check_version=check.version,
        status="NOTE",
        confidence=1.0,
        method="timing",
        reason=reason,
        evidence=evidence,
    )


def score_interruptions(check: CheckDefinition, turns: list[TurnDict]) -> CheckResultDict:
    """Every time the customer starts within INTERRUPTION_FOLLOW_ON_S of the
    agent's turn ending. A same-speaker follow-on turn is not an interruption.
    """
    ordered = sorted(turns, key=lambda t: t.get("start_s", 0.0))
    evidence: list[dict[str, Any]] = []
    descriptions: list[str] = []

    for previous, current in zip(ordered, ordered[1:], strict=False):
        if previous.get("speaker") != "agent" or current.get("speaker") != "customer":
            continue
        gap = current.get("start_s", 0.0) - previous.get("end_s", 0.0)
        if gap <= INTERRUPTION_FOLLOW_ON_S:
            evidence.append(_evidence(previous))
            evidence.append(_evidence(current))
            descriptions.append(f"at {current.get('start_s', 0.0):.1f}s (gap {gap:.2f}s)")

    if descriptions:
        reason = f"{check.title}: {', '.join(descriptions)}."
    else:
        reason = f"{check.title}: no fast follow-ons within {INTERRUPTION_FOLLOW_ON_S}s found."

    return CheckResultDict(
        check_id=check.check_id,
        check_version=check.version,
        status="NOTE",
        confidence=1.0,
        method="timing",
        reason=reason,
        evidence=evidence,
    )


def score_talk_ratio(check: CheckDefinition, turns: list[TurnDict]) -> CheckResultDict:
    """Share of total speaking time that was the agent, as a NOTE."""
    talk: dict[str, float] = {}
    for turn in turns:
        speaker = turn.get("speaker", "unknown")
        duration = max(0.0, turn.get("end_s", 0.0) - turn.get("start_s", 0.0))
        talk[speaker] = talk.get(speaker, 0.0) + duration

    total = sum(talk.values())
    agent_seconds = talk.get("agent", 0.0)
    fraction = agent_seconds / total if total > 0 else 0.0

    reason = f"{check.title}: agent spoke {fraction * 100:.1f}% of {total:.1f}s total."

    return CheckResultDict(
        check_id=check.check_id,
        check_version=check.version,
        status="NOTE",
        confidence=1.0,
        method="timing",
        reason=reason,
        evidence=[],
    )


_METRIC_TO_EVALUATOR = {
    "max_gap_seconds": score_dead_air,
    "overlap_seconds": score_interruptions,
    "agent_talk_fraction": score_talk_ratio,
}


def score_type_c_check(check: CheckDefinition, turns: list[TurnDict]) -> CheckResultDict:
    """Dispatch by metric. Always returns NOTE; never called by the gate for blocking."""
    evaluator = _METRIC_TO_EVALUATOR.get(check.metric)
    if evaluator is None:
        raise ValueError(f"no Type C evaluator for metric {check.metric!r}")
    return evaluator(check, turns)
