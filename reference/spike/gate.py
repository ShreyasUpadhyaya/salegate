import hashlib
from models import CheckResult, Transcript

DEAD_AIR_THRESHOLD_S = 20


def dead_air_notes(transcript: Transcript, check_id: str, check_version: int) -> list[CheckResult]:
    notes = []
    utts = sorted(transcript.utterances, key=lambda u: u.start_s)
    for a, b in zip(utts, utts[1:]):
        gap = b.start_s - a.end_s
        if gap > DEAD_AIR_THRESHOLD_S:
            notes.append(CheckResult(
                check_id, check_version, "NOTE", 1.0, "timing",
                f"Dead air: {gap:.0f} seconds at {a.end_s:.0f}s. Coaching note.",
                [{"utterance_idx": a.idx, "start_s": a.end_s}],
            ))
    return notes


def decide_gate(results: list[CheckResult], checks_by_id: dict, lead_id: str) -> dict:
    critical_fails = [r for r in results if r.status == "FAIL" and checks_by_id[r.check_id].critical]
    critical_reviews = [r for r in results if r.status == "REVIEW" and checks_by_id[r.check_id].critical]

    if critical_fails:
        decision = "HELD_TL"
    elif critical_reviews:
        decision = "QA_REVIEW"
    else:
        sample_bucket = int(hashlib.sha256(lead_id.encode()).hexdigest()[:8], 16) % 100
        decision = "QA_REVIEW" if sample_bucket < 5 else "AUTO_SUBMIT"

    return {
        "decision": decision,
        "critical_fails": [r.check_id for r in critical_fails],
        "critical_reviews": [r.check_id for r in critical_reviews],
    }
