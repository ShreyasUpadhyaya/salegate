import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fixtures import check_library_retailer1_v3, lead_3613790, transcript_3613790
from verbatim import score_verbatim
from factual import score_email_check, score_rate_check
from gate import dead_air_notes, decide_gate


def run_all():
    checks_by_id = {c.check_id: c for c in check_library_retailer1_v3}
    results = []
    for c in check_library_retailer1_v3:
        if c.check_id == "rates_and_charges":
            results.append(score_rate_check(c, transcript_3613790, lead_3613790))
        elif c.check_id == "email_captured":
            results.append(score_email_check(c, transcript_3613790, lead_3613790))
        elif c.check_id == "dead_air":
            results += dead_air_notes(transcript_3613790, c.check_id, c.version)
        else:
            results.append(score_verbatim(c, transcript_3613790))
    return results, checks_by_id


def test_disclaimer_passes():
    results, _ = run_all()
    r = next(r for r in results if r.check_id == "recording_disclaimer")
    assert r.status == "PASS"


def test_account_holder_passes():
    results, _ = run_all()
    r = next(r for r in results if r.check_id == "account_holder_confirmed")
    assert r.status == "PASS"


def test_dmo_passes():
    results, _ = run_all()
    r = next(r for r in results if r.check_id == "dmo_verbatim")
    assert r.status == "PASS"


def test_rate_mismatch_fails_with_both_values_in_reason():
    results, _ = run_all()
    r = next(r for r in results if r.check_id == "rates_and_charges")
    assert r.status == "FAIL"
    assert "28.6" in r.reason and "31.9" in r.reason
    assert r.evidence, "FAIL must carry evidence"


def test_email_mismatch_fails_with_both_values_in_reason():
    results, _ = run_all()
    r = next(r for r in results if r.check_id == "email_captured")
    assert r.status == "FAIL"
    assert "gmail" in r.reason and "gmial" in r.reason


def test_dead_air_is_a_note_not_a_block():
    # Fixture only carries highlight utterances, not a full transcript, so several
    # gaps read as dead air. In the real pipeline utterances are continuous, so this
    # will settle down. What matters here: dead air is always NOTE, never FAIL, and
    # never appears in critical_fails.
    results, checks_by_id = run_all()
    notes = [r for r in results if r.check_id == "dead_air"]
    assert notes and all(r.status == "NOTE" for r in notes)
    gate = decide_gate(results, checks_by_id, "3613790")
    assert "dead_air" not in gate["critical_fails"]


def test_gate_holds_for_tl_on_critical_fail():
    results, checks_by_id = run_all()
    gate = decide_gate(results, checks_by_id, "3613790")
    assert gate["decision"] == "HELD_TL"
    assert "rates_and_charges" in gate["critical_fails"]
    assert "email_captured" in gate["critical_fails"]


def test_script_evidence_points_at_the_right_moment():
    # Traceability: each script check must cite the utterance where it was said,
    # not the first window that happens to contain it.
    results, _ = run_all()
    starts = {r.check_id: r.evidence[0]["start_s"] for r in results if r.evidence}
    assert starts["recording_disclaimer"] == 12
    assert starts["account_holder_confirmed"] == 161
    assert starts["dmo_verbatim"] == 595


def test_every_pass_has_evidence():
    results, _ = run_all()
    for r in results:
        if r.status == "PASS":
            assert r.evidence, f"{r.check_id} passed with no evidence"


if __name__ == "__main__":
    results, checks_by_id = run_all()
    print(f"{'check':<26}{'status':<8}{'conf':<6}reason")
    for r in results:
        print(f"{r.check_id:<26}{r.status:<8}{r.confidence:<6.2f}{r.reason}")
    gate = decide_gate(results, checks_by_id, "3613790")
    print("\nGate decision:", gate["decision"])
    print("Critical fails:", gate["critical_fails"])
