"""Phase 5: the check library loads, and versions resolve by the call date.

The checklist was derived from handout/transcript.pdf because CIMET supplied no
library export (DECISIONS D19).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.checks.library import (
    CheckDefinition,
    load_all,
    load_lead_fixture,
    resolve_for_date,
)

RETAILER = "PROVIDER_A"
CALL_DATE = date(2026, 9, 19)


def test_both_versions_load():
    versions = {c.version for c in load_all()}

    assert versions == {1, 2}


def test_every_check_has_a_type_and_an_id():
    for check in load_all():
        assert check.type in {"A", "B", "C"}
        assert check.check_id
        assert check.retailer == RETAILER


def test_the_demo_call_resolves_to_version_one():
    """Hard rule 8: versions resolve by the call date, not by today."""
    snapshot = resolve_for_date(CALL_DATE, RETAILER)

    assert snapshot.checks
    assert all(c.version == 1 for c in snapshot.checks)


def test_a_call_after_the_boundary_resolves_to_version_two():
    snapshot = resolve_for_date(date(2026, 10, 1), RETAILER)

    assert all(c.version == 2 for c in snapshot.checks)


def test_the_boundary_is_exact_on_both_sides():
    last_v1 = resolve_for_date(date(2026, 9, 30), RETAILER)
    first_v2 = resolve_for_date(date(2026, 10, 1), RETAILER)

    assert {c.version for c in last_v1.checks} == {1}
    assert {c.version for c in first_v2.checks} == {2}


def test_the_disclaimer_wording_changes_between_versions():
    v1 = resolve_for_date(CALL_DATE, RETAILER).by_id("recording_disclaimer")
    v2 = resolve_for_date(date(2026, 10, 1), RETAILER).by_id("recording_disclaimer")

    assert v1 is not None and v2 is not None
    assert v1.approved_text != v2.approved_text
    assert "consent" in (v2.approved_text or "")


def test_a_date_before_the_library_starts_resolves_to_nothing():
    assert resolve_for_date(date(2025, 12, 31), RETAILER).checks == []


def test_the_snapshot_hash_is_stable_and_version_specific():
    first = resolve_for_date(CALL_DATE, RETAILER)
    again = resolve_for_date(CALL_DATE, RETAILER)
    later = resolve_for_date(date(2026, 10, 1), RETAILER)

    assert first.snapshot_hash == again.snapshot_hash
    assert first.snapshot_hash != later.snapshot_hash


def test_a_datetime_resolves_the_same_as_its_date():
    from_datetime = resolve_for_date(datetime(2026, 9, 19, 10, 5), RETAILER)
    from_date = resolve_for_date(CALL_DATE, RETAILER)

    assert from_datetime.snapshot_hash == from_date.snapshot_hash


def test_all_three_check_types_are_present():
    snapshot = resolve_for_date(CALL_DATE, RETAILER)

    assert snapshot.of_type("A")
    assert snapshot.of_type("B")
    assert snapshot.of_type("C")


def test_the_critical_checks_are_the_ones_that_should_hold_a_sale():
    critical = resolve_for_date(CALL_DATE, RETAILER).critical_ids

    assert "recording_disclaimer" in critical
    assert "ongoing_monthly_price" in critical
    assert "customer_email" in critical
    # Type C is coaching only and must never block.
    assert "dead_air" not in critical
    assert "talk_ratio" not in critical


def test_type_c_checks_never_block():
    for check in resolve_for_date(CALL_DATE, RETAILER).of_type("C"):
        assert check.blocks is False
        assert check.critical is False


def test_the_disclaimer_carries_its_ordering_rule():
    """Consent is a check, and it must come before any data collection."""
    disclaimer = resolve_for_date(CALL_DATE, RETAILER).by_id("recording_disclaimer")

    assert disclaimer is not None
    assert disclaimer.ordering is not None
    assert disclaimer.ordering["rule"] == "before_personal_data"
    assert "date of birth" in disclaimer.ordering["personal_data_markers"]


def test_every_type_a_check_has_approved_text_and_a_speaker():
    for check in resolve_for_date(CALL_DATE, RETAILER).of_type("A"):
        assert check.approved_text, f"{check.check_id} has no approved text"
        assert check.speaker == "agent"


def test_every_type_b_check_names_the_field_it_compares():
    for check in resolve_for_date(CALL_DATE, RETAILER).of_type("B"):
        assert check.field, f"{check.check_id} names no field"
        assert check.source in {"crm", "rate_card"}


def test_a_derived_check_says_so():
    """Consent to switch is not in the source call, so it must be flagged."""
    consent = resolve_for_date(CALL_DATE, RETAILER).by_id("consent_to_switch")

    assert consent is not None
    assert consent.derived is True
    assert consent.source_note


def test_an_unknown_check_type_is_rejected(tmp_path):
    import json

    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "retailer": "X",
                "version": 1,
                "effective_from": "2026-01-01",
                "effective_to": None,
                "checks": [{"check_id": "x", "type": "Z"}],
            }
        ),
        encoding="utf-8",
    )

    from app.checks.library import load_library_file

    with pytest.raises(ValueError, match="type Z"):
        load_library_file(bad)


def test_is_live_on_treats_an_open_window_as_still_current():
    check = CheckDefinition(
        check_id="x",
        version=1,
        retailer="X",
        type="A",
        effective_from=date(2026, 1, 1),
        effective_to=None,
    )

    assert check.is_live_on(date(2030, 1, 1)) is True
    assert check.is_live_on(date(2025, 1, 1)) is False


def test_the_lead_fixture_is_marked_synthetic_and_carries_the_recorded_values():
    lead = load_lead_fixture("L-DEMO-1")

    assert lead["synthetic"] is True
    assert lead["crm_fields"]["email"] == "jordan.avery@example.com"
    assert lead["crm_fields"]["dob"] == "1990-03-14"
    assert "12 Sample Street" in lead["crm_fields"]["service_address"]
    assert lead["rate_card"]["ongoing_price_monthly"] == 72.90
    assert lead["rate_card"]["promo_price_monthly"] == 42.90
    assert lead["rate_card"]["modem_model"] == "Netcomm CF40"


def test_the_fixture_rate_card_disagrees_with_what_the_agent_said():
    """The demo turns on this gap: 79.90 spoken against 72.90 on the rate card."""
    lead = load_lead_fixture("L-DEMO-1")

    assert lead["rate_card"]["ongoing_price_monthly"] == 72.90
    assert "79.90" in lead["expected_outcome"]["ongoing_monthly_price"]
