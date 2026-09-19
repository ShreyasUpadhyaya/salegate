"""Check library loader. Versions resolve by the call date, never by today.

The library ships as tracked JSON under app/checks/library/. CIMET provided no
check-library export, so the checklist was derived from handout/transcript.pdf
(DECISIONS D19). The loader is deliberately dumb: it reads files, validates
shape, and answers "which checks were live on this date".
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

LIBRARY_DIR = Path(__file__).resolve().parent / "library"

VALID_TYPES = {"A", "B", "C"}


class CheckDefinition(BaseModel):
    """One check at one version. The shape every evaluator receives."""

    check_id: str
    version: int
    retailer: str
    type: str
    critical: bool = False
    fatal: bool = False
    weight: float = 0.0
    title: str = ""

    # Type A
    approved_text: str | None = None
    alternates: list[str] = Field(default_factory=list)
    speaker: str | None = None
    ordering: dict[str, Any] | None = None
    match_mode: str | None = None  # verbatim | coverage | confirmation, see D20

    # Type B
    field: str | None = None
    source: str | None = None
    unit: str | None = None
    tolerance: float | None = None
    match: str | None = None

    # Type C
    metric: str | None = None
    threshold_config: str | None = None
    blocks: bool = True

    reason_pass: str = ""
    reason_fail: str = ""
    reason_note: str = ""
    derived: bool = False
    source_note: str = ""

    effective_from: date
    effective_to: date | None = None
    content_hash: str = ""

    def is_live_on(self, when: date) -> bool:
        """Was this version in force on this date? Both bounds inclusive."""
        if when < self.effective_from:
            return False
        return self.effective_to is None or when <= self.effective_to


class CheckLibrarySnapshot(BaseModel):
    """Every check live on one date, plus a hash of exactly that set."""

    retailer: str
    as_of: date
    checks: list[CheckDefinition]
    snapshot_hash: str

    def by_id(self, check_id: str) -> CheckDefinition | None:
        for check in self.checks:
            if check.check_id == check_id:
                return check
        return None

    @property
    def critical_ids(self) -> set[str]:
        return {c.check_id for c in self.checks if c.critical}

    def of_type(self, type_: str) -> list[CheckDefinition]:
        return [c for c in self.checks if c.type == type_]


def _content_hash(payload: dict[str, Any]) -> str:
    """Stable hash of one check's definition, ignoring key order."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_library_file(path: Path) -> list[CheckDefinition]:
    """Read one library JSON file into check definitions."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    retailer = raw["retailer"]
    version = int(raw["version"])
    effective_from = _parse_date(raw["effective_from"])
    effective_to = _parse_date(raw.get("effective_to"))

    checks: list[CheckDefinition] = []
    for entry in raw["checks"]:
        if entry["type"] not in VALID_TYPES:
            raise ValueError(f"{path.name}: check {entry['check_id']} has type {entry['type']}")
        checks.append(
            CheckDefinition(
                **entry,
                version=version,
                retailer=retailer,
                effective_from=effective_from,
                effective_to=effective_to,
                content_hash=_content_hash(entry),
            )
        )
    return checks


@lru_cache(maxsize=4)
def load_all(library_dir: Path = LIBRARY_DIR) -> tuple[CheckDefinition, ...]:
    """Every check version on disk. Lead fixtures are not checks, so skipped."""
    definitions: list[CheckDefinition] = []
    for path in sorted(library_dir.glob("*.json")):
        if path.name.startswith("lead_"):
            continue
        definitions.extend(load_library_file(path))
    return tuple(definitions)


def resolve_for_date(
    when: date | datetime,
    retailer: str,
    library_dir: Path = LIBRARY_DIR,
) -> CheckLibrarySnapshot:
    """The checks that were live for this retailer on this date.

    This is hard rule 8: a call is always scored against the checklist that was
    in force when it happened, so rescoring an old call after the checklist
    changes gives the same answer.
    """
    if isinstance(when, datetime):
        when = when.date()

    live = [
        check
        for check in load_all(library_dir)
        if check.retailer == retailer and check.is_live_on(when)
    ]

    seen: dict[str, CheckDefinition] = {}
    for check in live:
        current = seen.get(check.check_id)
        # Two versions live on one date means overlapping windows, which is a
        # library bug. Take the newest and let the hash record what was used.
        if current is None or check.version > current.version:
            seen[check.check_id] = check

    checks = sorted(seen.values(), key=lambda c: (c.type, c.check_id))
    digest = hashlib.sha256(
        "|".join(f"{c.check_id}@{c.version}:{c.content_hash}" for c in checks).encode("utf-8")
    ).hexdigest()

    return CheckLibrarySnapshot(
        retailer=retailer, as_of=when, checks=checks, snapshot_hash=digest
    )


def load_lead_fixture(lead_id: str, library_dir: Path = LIBRARY_DIR) -> dict[str, Any]:
    """A tracked synthetic lead, with its CRM fields and rate card."""
    path = library_dir / f"lead_{lead_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no fixture for lead {lead_id}")
    return json.loads(path.read_text(encoding="utf-8"))
