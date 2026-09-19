from rapidfuzz import fuzz
from models import CheckDefinition, CheckResult, Transcript

PASS_THRESHOLD = 88
REVIEW_THRESHOLD = 72


def score_verbatim(check: CheckDefinition, transcript: Transcript) -> CheckResult:
    """Slide a 1 to 3 utterance window over agent speech, score vs the approved script."""
    agent_utts = [u for u in transcript.utterances if u.speaker == "agent"]
    # Review fix: an earlier version kept the first window to hit the top score. A 3-utterance
    # window starting at the disclaimer also "contains" later scripts, so every check pointed
    # at 12s. Ties now go to the shortest window, so evidence lands on the right utterance.
    best_key = (-1.0, 0)
    best_score = 0.0
    best_window: list = []
    for i in range(len(agent_utts)):
        for span in (1, 2, 3):
            window = agent_utts[i:i + span]
            if len(window) < span:
                continue
            joined = " ".join(u.text for u in window)
            score = max(
                fuzz.partial_ratio(joined.lower(), check.script_text.lower()),
                fuzz.token_set_ratio(joined.lower(), check.script_text.lower()),
            )
            key = (score, -span)
            if key > best_key:
                best_key = key
                best_score = score
                best_window = window

    avg_conf = sum(u.confidence for u in best_window) / len(best_window) if best_window else 0.0
    evidence = [
        {"utterance_idx": u.idx, "speaker": u.speaker, "start_s": u.start_s, "end_s": u.end_s, "text": u.text}
        for u in best_window
    ]

    if best_score >= PASS_THRESHOLD:
        status = "PASS"
        reason = f"{check.label}: matched at {best_window[0].start_s:.0f}s (score {best_score:.0f})."
    elif best_score >= REVIEW_THRESHOLD:
        status = "REVIEW"
        reason = f"{check.label}: partial match at {best_window[0].start_s:.0f}s (score {best_score:.0f}), needs a human."
    else:
        status = "FAIL"
        reason = f"{check.label}: no adequate match found (best score {best_score:.0f})."

    if avg_conf < 0.75 and status in ("PASS", "FAIL"):
        status = "REVIEW"
        reason += " Low transcription confidence, routed to review."

    return CheckResult(
        check_id=check.check_id, check_version=check.version, status=status,
        confidence=avg_conf, method="fuzzy", reason=reason, evidence=evidence,
    )
