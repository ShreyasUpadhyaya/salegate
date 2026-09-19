"""Type B evaluators: quoted facts compared against the CRM record and rate card.

Ported from reference/spike/factual.py per PLAN.md Phase 7. Every mention of a
tracked value is checked, not just the first: any mismatching mention is FAIL,
citing each one with its timestamp (PLAN.md Phase 7 prompt). A value the agent
was meant to quote but never mentioned at all is REVIEW, not PASS: hard rule 7
means a critical fact never mentioned cannot be assumed correct.

Rules:
- Money, term, speed and modem come from agent turns only (the agent is the one
  quoting the plan).
- DOB and address may be said by either speaker (the customer often confirms
  their own detail).
- Evidence contract matches Phase 6: utterance_id, speaker, start_s, end_s,
  text_redacted on every result.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rapidfuzz import fuzz

from app.checks.library import CheckDefinition
from app.checks.models import CheckResultDict, TurnDict
from app.checks.normalise import (
    address_parts,
    extract_address_span,
    extract_dob,
    extract_download_speed_mbps,
    extract_modem_model,
    extract_money_mentions,
    extract_promo_term_months,
    extract_spoken_email,
    normalise_state_names,
)

MODEM_FUZZY_THRESHOLD = 90
ADDRESS_FUZZY_THRESHOLD = 90

# Confidence assigned to a REVIEW raised because a critical fact was never
# mentioned at all. Deliberately not 0: the transcript itself may be fine, the
# call simply never covered the field.
NEVER_MENTIONED_CONFIDENCE = 0.5


def _agent_turns(turns: list[TurnDict]) -> list[TurnDict]:
    return [t for t in turns if t.get("speaker") == "agent"]


def _either_speaker_turns(turns: list[TurnDict]) -> list[TurnDict]:
    return [t for t in turns if t.get("speaker") in ("agent", "customer")]


def _turn_confidence(turn: TurnDict) -> float:
    conf = float(turn.get("avg_confidence", 0.0))
    if turn.get("speaker_source") == "script_alignment" and turn.get("speaker") == "unknown":
        conf = max(0.0, conf - 0.1)
    return conf


def _evidence_one(turn: TurnDict) -> dict[str, Any]:
    return {
        "utterance_id": turn.get("idx"),
        "speaker": turn.get("speaker"),
        "start_s": turn.get("start_s"),
        "end_s": turn.get("end_s"),
        "text_redacted": turn.get("text_redacted", ""),
    }


def _never_mentioned(check: CheckDefinition) -> CheckResultDict:
    reason = f"{check.title}: {check.field or 'value'} was never mentioned on the call."
    return CheckResultDict(
        check_id=check.check_id,
        check_version=check.version,
        status="REVIEW",
        confidence=NEVER_MENTIONED_CONFIDENCE,
        method="extract",
        reason=reason,
        evidence=[],
    )


def _score_numeric_mentions(
    check: CheckDefinition,
    turns: list[TurnDict],
    extractor: Callable[[str], list[float]],
    expected: float,
    unit: str,
    tolerance: float = 0.0,
) -> CheckResultDict:
    """Every mention of a numeric quote, compared to `expected` to the given tolerance.

    Any mismatching mention FAILs, citing every mismatch with its timestamp,
    per the Phase 7 prompt. A matching mention alongside a mismatching one
    still FAILs: the agent said two different numbers and only one is right.
    """
    mismatches: list[TurnDict] = []
    matches: list[TurnDict] = []
    for turn in _agent_turns(turns):
        for value in extractor(turn.get("text_redacted", "")):
            if abs(value - expected) <= tolerance:
                matches.append(turn)
            else:
                mismatches.append(turn)

    if mismatches:
        lines = [
            f"{t['start_s']:.1f}s" for t in mismatches
        ]
        reason = (
            f"{check.title}: quoted value does not match {expected} {unit} "
            f"(mismatched at {', '.join(lines)})."
        )
        evidence = [_evidence_one(t) for t in mismatches + matches]
        avg_conf = sum(_turn_confidence(t) for t in mismatches) / len(mismatches)
        return CheckResultDict(
            check_id=check.check_id,
            check_version=check.version,
            status="FAIL",
            confidence=round(avg_conf, 3),
            method="extract",
            reason=reason,
            evidence=evidence,
        )

    if matches:
        avg_conf = sum(_turn_confidence(t) for t in matches) / len(matches)
        status = "PASS"
        reason = f"{check.title}: quoted value matches {expected} {unit}."
        if avg_conf < 0.75:
            status = "REVIEW"
            reason += " Low transcription confidence, routed to review."
        return CheckResultDict(
            check_id=check.check_id,
            check_version=check.version,
            status=status,
            confidence=round(avg_conf, 3),
            method="extract",
            reason=reason,
            evidence=[_evidence_one(t) for t in matches],
        )

    return _never_mentioned(check)


_FIELD_TO_ROLE = {
    "promo_price_monthly": "promo",
    "ongoing_price_monthly": "ongoing",
}


def score_money_check(
    check: CheckDefinition, turns: list[TurnDict], rate_card: dict
) -> CheckResultDict:
    """Promo or ongoing monthly price vs the rate card, to the cent.

    A call quotes both prices, often in the same turn ("$42.90 a month, then
    $79.90 ongoing"), so mentions are filtered to the role this check cares
    about before comparing. An "unknown" mention (no nearby marker word found
    at all, in the whole turn) is still considered, since a call that states
    only one price with no qualifying phrase is still making a claim about it.
    But once the turn contains a confidently tagged mention of the OTHER role,
    a same-value "unknown" mention right next to it is noise from a marker
    search running out of room, not a second claim, and is dropped.
    """
    expected = float(rate_card[check.field])
    tolerance = float(check.tolerance or 0.0)
    wanted_role = _FIELD_TO_ROLE.get(check.field)
    other_role = "ongoing" if wanted_role == "promo" else "promo"

    def extractor(text: str) -> list[float]:
        mentions = extract_money_mentions(text)
        has_other = any(role == other_role for _, role in mentions)
        wanted = [value for value, role in mentions if role == wanted_role]
        if wanted:
            return wanted
        if has_other:
            # The turn already tagged a mention for the other price; an
            # untagged mention here almost certainly belongs to that other
            # price too (a trailing repeat), not to this check's field.
            return []
        return [value for value, role in mentions if role == "unknown"]

    return _score_numeric_mentions(check, turns, extractor, expected, "AUD/month", tolerance)


def score_promo_term_check(
    check: CheckDefinition, turns: list[TurnDict], rate_card: dict
) -> CheckResultDict:
    expected = float(rate_card[check.field])

    def extractor(text: str) -> list[float]:
        value = extract_promo_term_months(text)
        return [float(value)] if value is not None else []

    return _score_numeric_mentions(check, turns, extractor, expected, "months")


def score_download_speed_check(
    check: CheckDefinition, turns: list[TurnDict], rate_card: dict
) -> CheckResultDict:
    expected = float(rate_card[check.field])

    def extractor(text: str) -> list[float]:
        value = extract_download_speed_mbps(text)
        return [value] if value is not None else []

    return _score_numeric_mentions(check, turns, extractor, expected, "Mbps")


def score_modem_check(
    check: CheckDefinition, turns: list[TurnDict], rate_card: dict
) -> CheckResultDict:
    """Fuzzy match on the modem name, >= 90, since STT commonly mangles it."""
    expected = str(rate_card[check.field]).lower()
    mismatches: list[tuple[TurnDict, str]] = []
    matches: list[TurnDict] = []

    for turn in _agent_turns(turns):
        found = extract_modem_model(turn.get("text_redacted", ""))
        if found is None:
            continue
        score = fuzz.ratio(found.lower(), expected)
        if score >= MODEM_FUZZY_THRESHOLD:
            matches.append(turn)
        else:
            mismatches.append((turn, found))

    if mismatches:
        lines = [f"{t['start_s']:.1f}s ({found})" for t, found in mismatches]
        expected_modem = rate_card[check.field]
        reason = f"{check.title}: modem does not match {expected_modem} ({', '.join(lines)})."
        evidence = [_evidence_one(t) for t, _ in mismatches] + [_evidence_one(t) for t in matches]
        return CheckResultDict(
            check_id=check.check_id,
            check_version=check.version,
            status="FAIL",
            confidence=round(sum(_turn_confidence(t) for t, _ in mismatches) / len(mismatches), 3),
            method="extract",
            reason=reason,
            evidence=evidence,
        )

    if matches:
        avg_conf = sum(_turn_confidence(t) for t in matches) / len(matches)
        return CheckResultDict(
            check_id=check.check_id,
            check_version=check.version,
            status="PASS" if avg_conf >= 0.75 else "REVIEW",
            confidence=round(avg_conf, 3),
            method="extract",
            reason=f"{check.title}: modem matches {rate_card[check.field]}.",
            evidence=[_evidence_one(t) for t in matches],
        )

    return _never_mentioned(check)


def score_email_check(
    check: CheckDefinition, turns: list[TurnDict], crm: dict
) -> CheckResultDict:
    """Email read-back vs CRM, exact after lowercasing (span isolated first)."""
    expected = str(crm[check.field]).strip().lower()
    mismatches: list[tuple[TurnDict, str]] = []
    matches: list[TurnDict] = []

    for turn in _agent_turns(turns):
        found = extract_spoken_email(turn.get("text_redacted", ""))
        if found is None:
            continue
        if found == expected:
            matches.append(turn)
        else:
            mismatches.append((turn, found))

    if mismatches:
        lines = [f"{t['start_s']:.1f}s ({found!r})" for t, found in mismatches]
        reason = f"{check.title}: read back does not match CRM {expected!r} ({', '.join(lines)})."
        evidence = [_evidence_one(t) for t, _ in mismatches] + [_evidence_one(t) for t in matches]
        avg_conf = sum(_turn_confidence(t) for t, _ in mismatches) / len(mismatches)
        return CheckResultDict(
            check_id=check.check_id,
            check_version=check.version,
            status="FAIL",
            confidence=round(avg_conf, 3),
            method="extract",
            reason=reason,
            evidence=evidence,
        )

    if matches:
        avg_conf = sum(_turn_confidence(t) for t in matches) / len(matches)
        status = "PASS" if avg_conf >= 0.75 else "REVIEW"
        return CheckResultDict(
            check_id=check.check_id,
            check_version=check.version,
            status=status,
            confidence=round(avg_conf, 3),
            method="extract",
            reason=f"{check.title}: read back matches CRM.",
            evidence=[_evidence_one(t) for t in matches],
        )

    return _never_mentioned(check)


def score_dob_check(
    check: CheckDefinition, turns: list[TurnDict], crm: dict
) -> CheckResultDict:
    """DOB vs CRM. Either speaker may state it (D19 rule)."""
    expected = str(crm[check.field]).strip()
    mismatches: list[tuple[TurnDict, str]] = []
    matches: list[TurnDict] = []

    for turn in _either_speaker_turns(turns):
        found = extract_dob(turn.get("text_redacted", ""))
        if found is None:
            continue
        if found == expected:
            matches.append(turn)
        else:
            mismatches.append((turn, found))

    if mismatches:
        lines = [f"{t['start_s']:.1f}s ({found})" for t, found in mismatches]
        reason = f"{check.title}: date does not match CRM {expected} ({', '.join(lines)})."
        evidence = [_evidence_one(t) for t, _ in mismatches] + [_evidence_one(t) for t in matches]
        avg_conf = sum(_turn_confidence(t) for t, _ in mismatches) / len(mismatches)
        return CheckResultDict(
            check_id=check.check_id,
            check_version=check.version,
            status="FAIL",
            confidence=round(avg_conf, 3),
            method="extract",
            reason=reason,
            evidence=evidence,
        )

    if matches:
        avg_conf = sum(_turn_confidence(t) for t in matches) / len(matches)
        status = "PASS" if avg_conf >= 0.75 else "REVIEW"
        return CheckResultDict(
            check_id=check.check_id,
            check_version=check.version,
            status=status,
            confidence=round(avg_conf, 3),
            method="extract",
            reason=f"{check.title}: date of birth matches CRM.",
            evidence=[_evidence_one(t) for t in matches],
        )

    return _never_mentioned(check)


def score_address_check(
    check: CheckDefinition, turns: list[TurnDict], crm: dict
) -> CheckResultDict:
    """Street number and postcode exact, the rest fuzzy token_set >= 90.

    Either speaker may state it (D19 rule): the customer usually confirms their
    own address.
    """
    expected = str(crm[check.field]).strip()
    expected_number, expected_postcode = address_parts(expected)

    mismatches: list[tuple[TurnDict, str]] = []
    matches: list[TurnDict] = []

    candidate_windows: list[list[TurnDict]] = []
    eligible = _either_speaker_turns(turns)
    for index, turn in enumerate(eligible):
        candidate_windows.append([turn])
        if index + 1 >= len(eligible):
            continue
        following = eligible[index + 1]
        if (
            following.get("speaker") == turn.get("speaker")
            and float(following.get("start_s", 0.0))
            <= float(turn.get("end_s", 0.0)) + 0.5
        ):
            candidate_windows.append([turn, following])

    matched_turn_ids: set[int] = set()
    for window in candidate_windows:
        found = extract_address_span(
            " ".join(turn.get("text_redacted", "") for turn in window)
        )
        if found is None:
            continue
        found_number, found_postcode = address_parts(found)
        number_ok = expected_number is not None and found_number == expected_number
        postcode_ok = expected_postcode is not None and found_postcode == expected_postcode
        fuzzy_score = fuzz.token_set_ratio(
            normalise_state_names(found), normalise_state_names(expected)
        )

        if number_ok and postcode_ok and fuzzy_score >= ADDRESS_FUZZY_THRESHOLD:
            for turn in window:
                turn_id = id(turn)
                if turn_id not in matched_turn_ids:
                    matches.append(turn)
                    matched_turn_ids.add(turn_id)
        else:
            if not any(id(turn) in matched_turn_ids for turn in window):
                mismatches.append((window[0], found))

    mismatches = [
        (turn, found)
        for turn, found in mismatches
        if id(turn) not in matched_turn_ids
    ]

    if mismatches:
        lines = [f"{t['start_s']:.1f}s ({found!r})" for t, found in mismatches]
        reason = f"{check.title}: address does not match CRM {expected!r} ({', '.join(lines)})."
        evidence = [_evidence_one(t) for t, _ in mismatches] + [_evidence_one(t) for t in matches]
        avg_conf = sum(_turn_confidence(t) for t, _ in mismatches) / len(mismatches)
        return CheckResultDict(
            check_id=check.check_id,
            check_version=check.version,
            status="FAIL",
            confidence=round(avg_conf, 3),
            method="extract",
            reason=reason,
            evidence=evidence,
        )

    if matches:
        avg_conf = sum(_turn_confidence(t) for t in matches) / len(matches)
        status = "PASS" if avg_conf >= 0.75 else "REVIEW"
        return CheckResultDict(
            check_id=check.check_id,
            check_version=check.version,
            status=status,
            confidence=round(avg_conf, 3),
            method="extract",
            reason=f"{check.title}: address matches CRM.",
            evidence=[_evidence_one(t) for t in matches],
        )

    return _never_mentioned(check)


_FIELD_TO_CHECK = {
    "promo_price_monthly": score_money_check,
    "ongoing_price_monthly": score_money_check,
    "promo_term_months": score_promo_term_check,
    "download_speed_mbps": score_download_speed_check,
    "modem_model": score_modem_check,
    "email": score_email_check,
    "dob": score_dob_check,
    "service_address": score_address_check,
}


def score_type_b_check(
    check: CheckDefinition, turns: list[TurnDict], lead: dict
) -> CheckResultDict:
    """Dispatch by field. `lead` carries both `crm_fields` and `rate_card`."""
    evaluator = _FIELD_TO_CHECK.get(check.field)
    if evaluator is None:
        raise ValueError(f"no Type B evaluator for field {check.field!r}")

    source = lead["rate_card"] if check.source == "rate_card" else lead["crm_fields"]
    return evaluator(check, turns, source)
