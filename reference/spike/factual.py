from rapidfuzz import fuzz
from models import CheckDefinition, CheckResult, Lead, Transcript
from normalise import extract_rate_c_per_kwh, normalise_spoken_email

RATE_TOLERANCE_C = 0.05


def score_rate_check(check: CheckDefinition, transcript: Transcript, lead: Lead) -> CheckResult:
    agent_utts = [u for u in transcript.utterances if u.speaker == "agent"]
    for u in agent_utts:
        quoted = extract_rate_c_per_kwh(u.text)
        if quoted is not None:
            plan = lead.plan_peak_rate_c_per_kwh
            evidence = [{"utterance_idx": u.idx, "speaker": u.speaker, "start_s": u.start_s, "text": u.text}]
            if abs(quoted - plan) <= RATE_TOLERANCE_C:
                return CheckResult(check.check_id, check.version, "PASS", u.confidence, "extract",
                                    f"Quoted peak rate {quoted}c matches plan {plan}c/kWh.", evidence)
            return CheckResult(check.check_id, check.version, "FAIL", u.confidence, "extract",
                                f"Agent said peak is {quoted}c at {u.start_s:.0f}s. Plan on the lead is "
                                f"{plan}c/kWh. Mismatch.", evidence)
    return CheckResult(check.check_id, check.version, "FAIL", 0.5, "extract",
                        "Peak rate was never confirmed on the call.", [])


def score_email_check(check: CheckDefinition, transcript: Transcript, lead: Lead) -> CheckResult:
    agent_utts = [u for u in transcript.utterances if u.speaker == "agent"]
    for u in agent_utts:
        spoken = normalise_spoken_email(u.text)
        if spoken is not None:
            evidence = [{"utterance_idx": u.idx, "speaker": u.speaker, "start_s": u.start_s, "text": u.text}]
            similarity = fuzz.ratio(spoken, lead.crm_email.lower())
            if spoken == lead.crm_email.lower():
                return CheckResult(check.check_id, check.version, "PASS", u.confidence, "extract",
                                    "Email read-back matches CRM.", evidence)
            if similarity >= 85:
                return CheckResult(check.check_id, check.version, "FAIL", u.confidence, "extract",
                                    f"Agent read back \"{spoken}\" at {u.start_s:.0f}s. CRM field says "
                                    f"\"{lead.crm_email}\". Mismatch.", evidence)
            return CheckResult(check.check_id, check.version, "REVIEW", u.confidence, "extract",
                                "Email read-back differs substantially from CRM, needs a human.", evidence)
    return CheckResult(check.check_id, check.version, "FAIL", 0.5, "extract",
                        "Email was never confirmed on the call.", [])
