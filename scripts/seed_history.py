"""Seed synthetic scored history so the dashboards have something to show.

One real call cannot show weekly trends (DECISIONS D12), so this generates
scored leads directly: no audio, no transcription, just Score and CheckResult
rows built from the real library, spread across a few agents and dates. Every
seeded lead's id is prefixed SEED- and its retailer field is unchanged, so the
UI can label this as seeded demo data rather than pass it off as real.

    uv run python scripts/seed_history.py
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.checks.library import load_all  # noqa: E402
from app.db import SessionLocal, create_all  # noqa: E402
from app.models import CheckResult, Lead, Score  # noqa: E402
from app.scoring.gate import decide_gate  # noqa: E402

AGENTS = ["A-001", "A-002", "A-003", "A-004"]
RETAILER = "PROVIDER_A"
DAYS_BACK = 28
CALLS_PER_DAY = 3
RANDOM_SEED = 20260919  # reproducible seed, not a security key


def _call_outcome() -> str:
    """Which way this whole call leans: clean, one review, or one fail.

    Chosen once per call, not once per check, so the shape matches a real
    queue: mostly clean, a real minority held or reviewed, rather than every
    call almost certainly failing something once a dozen independent coin
    flips are combined.
    """
    return random.choices(["clean", "clean", "clean", "clean", "review", "fail"], k=1)[0]


def _status_for_check(critical: bool, outcome: str) -> str:
    if outcome == "fail" and critical and random.random() < 0.35:
        return "FAIL"
    if outcome == "review" and critical and random.random() < 0.35:
        return "REVIEW"
    return "PASS"


def seed() -> int:
    random.seed(RANDOM_SEED)  # re-seeded on every call, so repeated runs agree
    create_all()
    session = SessionLocal()

    checks = [c for c in load_all() if c.retailer == RETAILER]
    if not checks:
        print(f"No checks found for retailer {RETAILER}; run Phase 5 first.")
        return 1

    # A representative library snapshot at any of these dates: they all fall
    # inside v1's window (2026-01-01 to 2026-09-30), so one snapshot suffices.
    from app.checks.library import resolve_for_date

    snapshot = resolve_for_date(datetime(2026, 6, 1).date(), RETAILER)

    created = 0
    for day_offset in range(DAYS_BACK):
        call_date = datetime.now() - timedelta(days=day_offset)
        for _ in range(CALLS_PER_DAY):
            agent_id = random.choice(AGENTS)
            lead_id = f"SEED-{call_date.strftime('%Y%m%d')}-{agent_id}-{created}"

            lead = Lead(
                lead_id=lead_id,
                retailer=RETAILER,
                agent_id=agent_id,
                tl_id="TL-001",
                site="Seeded",
                campaign="Seeded history",
                call_started_at=call_date,
                crm_fields={},
                status="SEEDED",
            )
            session.add(lead)
            session.flush()

            method_by_type = {"A": "fuzzy", "B": "extract", "C": "timing"}
            outcome = _call_outcome()
            results = []
            for check in snapshot.checks:
                if check.type == "C":
                    status = "NOTE"
                else:
                    status = _status_for_check(check.critical, outcome)
                results.append(
                    {
                        "check_id": check.check_id,
                        "check_version": check.version,
                        "status": status,
                        "confidence": round(random.uniform(0.8, 1.0), 3),
                        "method": method_by_type[check.type],
                        "reason": f"Seeded {status.lower()} for demo history.",
                        "evidence": (
                            [
                                {
                                    "utterance_id": 0,
                                    "speaker": "agent",
                                    "start_s": 0.0,
                                    "end_s": 1.0,
                                    "text_redacted": "(seeded, no real transcript)",
                                }
                            ]
                            if status != "REVIEW"
                            else []
                        ),
                    }
                )

            gate = decide_gate(results, snapshot, lead_id)

            score = Score(
                lead_id=lead_id,
                library_snapshot_hash=snapshot.snapshot_hash,
                scored_at=call_date,
                decision=gate["decision"],
                sampled_for_qa=gate["sampled_for_qa"],
            )
            session.add(score)
            session.flush()

            for result in results:
                session.add(CheckResult(score_id=score.id, **result))

            created += 1

    session.commit()
    session.close()
    print(f"Seeded {created} synthetic leads across {len(AGENTS)} agents over {DAYS_BACK} days.")
    print("Labelled SEED- in lead_id, status SEEDED. Not real calls, see DECISIONS D12.")
    return 0


if __name__ == "__main__":
    raise SystemExit(seed())
