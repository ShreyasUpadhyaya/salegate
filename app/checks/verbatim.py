"""Type A evaluators: script and behaviour checks against agent speech.

Ported from reference/spike/verbatim.py per PLAN.md Phase 6, carrying forward
both fixes already found there: span isolation before normalising (applied in
app/ingest/speakers.py for turn splitting, and here by scoring whole turns
rather than substrings) and shortest-window tie-break, so evidence timestamps
land on the right turn instead of the first window that happens to score
highest (README-SPIKE.md bug 3).

Three match modes, chosen by what each check means, never by what makes one
call pass (DECISIONS D20):
  verbatim     short fixed lines: disclaimer, self-identification.
  coverage     long reads: plan key information, total minimum cost. Scored by
               the fraction of approved sentences actually said.
  confirmation a yes/no exchange: account holder, consent to switch. The agent
               question must match, and a customer affirmative must follow.

Evaluators take (check, turns, lead) and return a CheckResultDict. No DB access.
"""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz

from app.checks.library import CheckDefinition
from app.checks.models import CheckResultDict, TurnDict
from app.config import LOW_STT_CONFIDENCE, VERBATIM_PASS_THRESHOLD, VERBATIM_REVIEW_THRESHOLD

# Coverage checks (long reads) need this fraction of their sentences said.
COVERAGE_PASS_FRACTION = 0.90
# A sentence counts as "said" at this score, same scale as the verbatim scores.
COVERAGE_SENTENCE_THRESHOLD = 80

# A confirmation question must score at least this well to count as asked.
CONFIRMATION_QUESTION_THRESHOLD = 80
# How many customer turns after the question count as "the reply".
CONFIRMATION_REPLY_WINDOW = 2

_AFFIRMATIVE = re.compile(
    r"\b(yes|yeah|yep|yup|correct|that'?s (?:right|correct|it|me)|i agree|i am|"
    r"i do|sounds good|okay|ok)\b",
    re.IGNORECASE,
)

# Unknown speaker means an unresolved turn (DECISIONS D18). A check that leans
# on it must not be as confident as a clean agent attribution (hard rule 7).
UNKNOWN_SPEAKER_PENALTY = 0.1


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _agent_turns(turns: list[TurnDict]) -> list[TurnDict]:
    return [t for t in turns if t.get("speaker") == "agent"]


def _turn_confidence(turn: TurnDict) -> float:
    """Average word confidence on this turn, penalised if its speaker is unresolved."""
    conf = float(turn.get("avg_confidence", 0.0))
    if turn.get("speaker_source") == "script_alignment" and turn.get("speaker") == "unknown":
        conf = max(0.0, conf - UNKNOWN_SPEAKER_PENALTY)
    return conf


def _evidence(turns: list[TurnDict]) -> list[dict[str, Any]]:
    return [
        {
            "utterance_id": t.get("idx"),
            "speaker": t.get("speaker"),
            "start_s": t.get("start_s"),
            "end_s": t.get("end_s"),
            "text_redacted": t.get("text_redacted", ""),
        }
        for t in turns
    ]


def _score_window(joined: str, approved: str) -> float:
    a, b = _normalise(joined), _normalise(approved)
    return max(fuzz.partial_ratio(a, b), fuzz.token_set_ratio(a, b))


def _best_window(
    agent_turns: list[TurnDict], approved: str, spans: tuple[int, ...] = (1, 2, 3, 4)
) -> tuple[float, list[TurnDict]]:
    """Slide a window over agent turns, ties go to the shortest window.

    Carries forward the spike's bug 3 fix: an earlier version kept the first
    window to hit the top score, so every check's evidence pointed at the same
    early timestamp. Sorting by (score, -span) makes the shortest tied window
    win, which keeps evidence on the turn that actually matches.
    """
    best_key = (-1.0, 0)
    best_score = 0.0
    best_window: list[TurnDict] = []
    for i in range(len(agent_turns)):
        for span in spans:
            window = agent_turns[i : i + span]
            if len(window) < span:
                continue
            joined = " ".join(t.get("text_redacted", "") for t in window)
            score = _score_window(joined, approved)
            key = (score, -span)
            if key > best_key:
                best_key = key
                best_score = score
                best_window = window
    return best_score, best_window


def _confidence_downgrade(status: str, avg_conf: float, reason: str) -> tuple[str, str]:
    """Hard rule 7: a critical check never PASSes on low confidence."""
    if avg_conf < LOW_STT_CONFIDENCE and status in ("PASS", "FAIL"):
        return "REVIEW", reason + " Low transcription confidence, routed to review."
    return status, reason


def score_verbatim_check(check: CheckDefinition, turns: list[TurnDict]) -> CheckResultDict:
    """Short fixed line: disclaimer, self-identification.

    The best of the approved text and any alternates wins, since some checks
    (account holder confirmation in v1) accept more than one real phrasing.
    """
    agent_turns = _agent_turns(turns)
    candidates = [check.approved_text] + list(check.alternates)
    candidates = [c for c in candidates if c]

    best_score, best_window = 0.0, []
    for candidate in candidates:
        score, window = _best_window(agent_turns, candidate)
        if score > best_score:
            best_score, best_window = score, window

    avg_conf = (
        sum(_turn_confidence(t) for t in best_window) / len(best_window) if best_window else 0.0
    )

    if best_score >= VERBATIM_PASS_THRESHOLD:
        status = "PASS"
        start = best_window[0]["start_s"]
        reason = f"{check.title}: matched at {start:.1f}s (score {best_score:.0f})."
    elif best_score >= VERBATIM_REVIEW_THRESHOLD:
        status = "REVIEW"
        reason = f"{check.title}: partial match (score {best_score:.0f}), needs review."
    else:
        status = "FAIL"
        fail_reason = check.reason_fail or "no adequate match found"
        reason = f"{check.title}: {fail_reason} (best score {best_score:.0f})."

    status, reason = _confidence_downgrade(status, avg_conf, reason)

    return CheckResultDict(
        check_id=check.check_id,
        check_version=check.version,
        status=status,
        confidence=round(avg_conf, 3),
        method="fuzzy",
        reason=reason,
        evidence=_evidence(best_window) if best_window else [],
    )


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|,\s+(?=and\s)|;\s+", text)
    return [p.strip() for p in parts if p.strip()]


def score_coverage_check(check: CheckDefinition, turns: list[TurnDict]) -> CheckResultDict:
    """Long read: what fraction of the approved sentences did the agent say.

    Missing sentences are named verbatim in the reason, so a TL sees exactly
    what was skipped rather than a bare score.
    """
    agent_turns = _agent_turns(turns)
    joined_agent = _normalise(" ".join(t.get("text_redacted", "") for t in agent_turns))
    sentences = _split_sentences(check.approved_text or "")

    said: list[str] = []
    missing: list[str] = []
    sentence_scores: list[float] = []
    for sentence in sentences:
        score = fuzz.partial_ratio(_normalise(sentence), joined_agent)
        sentence_scores.append(score)
        (said if score >= COVERAGE_SENTENCE_THRESHOLD else missing).append(sentence)

    fraction = len(said) / len(sentences) if sentences else 0.0

    # Evidence is the agent turns that best cover the approved text, same
    # shortest-window tie-break as verbatim, so timestamps are still precise.
    _, best_window = _best_window(agent_turns, check.approved_text or "", spans=(1, 2, 3, 4, 6, 8))
    avg_conf = (
        sum(_turn_confidence(t) for t in best_window) / len(best_window) if best_window else 0.0
    )

    if fraction >= COVERAGE_PASS_FRACTION:
        status = "PASS"
        reason = f"{check.title}: {len(said)}/{len(sentences)} sentences said."
    else:
        status = "FAIL" if fraction < 0.5 else "REVIEW"
        missing_text = " | ".join(missing) if missing else "unscored"
        reason = (
            f"{check.title}: only {len(said)}/{len(sentences)} sentences said. "
            f"Missing: {missing_text}"
        )

    status, reason = _confidence_downgrade(status, avg_conf, reason)

    return CheckResultDict(
        check_id=check.check_id,
        check_version=check.version,
        status=status,
        confidence=round(avg_conf, 3),
        method="fuzzy",
        reason=reason,
        evidence=_evidence(best_window) if best_window else [],
    )


def score_confirmation_check(check: CheckDefinition, turns: list[TurnDict]) -> CheckResultDict:
    """A question the agent asks, and an affirmative the customer gives back.

    The question must score at least CONFIRMATION_QUESTION_THRESHOLD, and one
    of the next CONFIRMATION_REPLY_WINDOW customer turns must read as an
    affirmative. Evidence cites both turns, since the check is really about
    the pair, not either one alone.
    """
    candidates = [check.approved_text] + list(check.alternates)
    candidates = [c for c in candidates if c]

    best_score = 0.0
    best_idx: int | None = None
    for i, turn in enumerate(turns):
        if turn.get("speaker") != "agent":
            continue
        text = turn.get("text_redacted", "")
        score = max(_score_window(text, c) for c in candidates)
        if score > best_score:
            best_score, best_idx = score, i

    if best_idx is None or best_score < CONFIRMATION_QUESTION_THRESHOLD:
        reason = f"{check.title}: {check.reason_fail or 'question was never asked'}."
        return CheckResultDict(
            check_id=check.check_id,
            check_version=check.version,
            status="FAIL",
            confidence=0.0,
            method="fuzzy",
            reason=reason,
            evidence=[],
        )

    question_turn = turns[best_idx]
    reply_turn = None
    seen_customer = 0
    for turn in turns[best_idx + 1 :]:
        if turn.get("speaker") != "customer":
            continue
        seen_customer += 1
        if _AFFIRMATIVE.search(turn.get("text_redacted", "")):
            reply_turn = turn
            break
        if seen_customer >= CONFIRMATION_REPLY_WINDOW:
            break

    evidence_turns = [question_turn] + ([reply_turn] if reply_turn else [])
    avg_conf = sum(_turn_confidence(t) for t in evidence_turns) / len(evidence_turns)

    if reply_turn is not None:
        status = "PASS"
        asked, confirmed = question_turn["start_s"], reply_turn["start_s"]
        pass_reason = check.reason_pass or "confirmed"
        reason = (
            f"{check.title}: {pass_reason} "
            f"(asked at {asked:.1f}s, confirmed at {confirmed:.1f}s)."
        )
    else:
        status = "FAIL"
        reason = (
            f"{check.title}: question asked at {question_turn['start_s']:.1f}s but no "
            f"affirmative reply followed within {CONFIRMATION_REPLY_WINDOW} customer turns."
        )

    status, reason = _confidence_downgrade(status, avg_conf, reason)

    return CheckResultDict(
        check_id=check.check_id,
        check_version=check.version,
        status=status,
        confidence=round(avg_conf, 3),
        method="fuzzy",
        reason=reason,
        evidence=_evidence(evidence_turns),
    )


def score_type_a_check(check: CheckDefinition, turns: list[TurnDict]) -> CheckResultDict:
    """Dispatch by match_mode. Evaluators take (check, turns) and return a result."""
    mode = check.match_mode or "verbatim"
    if mode == "coverage":
        return score_coverage_check(check, turns)
    if mode == "confirmation":
        return score_confirmation_check(check, turns)
    return score_verbatim_check(check, turns)


def score_disclaimer_ordering(
    check: CheckDefinition, turns: list[TurnDict], disclaimer_result: CheckResultDict
) -> CheckResultDict:
    """Consent is a check, and it must come before any data collection (hard rule 11).

    Re-scores the disclaimer result: if it passed on wording but a personal
    data question was asked first, it FAILs on ordering instead, with both
    timestamps in the reason.
    """
    if check.ordering is None or disclaimer_result["status"] not in ("PASS", "REVIEW"):
        return disclaimer_result
    if not disclaimer_result["evidence"]:
        return disclaimer_result

    disclaimer_start = disclaimer_result["evidence"][0]["start_s"]
    markers = check.ordering.get("personal_data_markers", [])

    for turn in turns:
        if turn.get("speaker") != "agent":
            continue
        if turn.get("start_s", 0.0) >= disclaimer_start:
            break
        text = _normalise(turn.get("text_redacted", ""))
        for marker in markers:
            if marker in text:
                return CheckResultDict(
                    check_id=check.check_id,
                    check_version=check.version,
                    status="FAIL",
                    confidence=disclaimer_result["confidence"],
                    method="timing",
                    reason=(
                        f"{check.title}: personal data ({marker!r}) requested at "
                        f"{turn['start_s']:.1f}s, before the disclaimer at "
                        f"{disclaimer_start:.1f}s."
                    ),
                    evidence=_evidence([turn]) + disclaimer_result["evidence"],
                )
    return disclaimer_result
