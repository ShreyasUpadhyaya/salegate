"""Rehearsal spike. Not the real repo. Tests the riskiest logic before build day."""
from dataclasses import dataclass, field


@dataclass
class Utterance:
    idx: int
    speaker: str  # agent | customer
    start_s: float
    end_s: float
    text: str
    confidence: float = 0.95


@dataclass
class Transcript:
    utterances: list[Utterance]


@dataclass
class CheckDefinition:
    check_id: str
    version: int
    type: str  # A | B | C
    critical: bool
    fatal: bool
    label: str
    script_text: str | None = None      # for type A
    field_name: str | None = None       # for type B, e.g. "peak_rate_c_per_kwh" or "email"


@dataclass
class CheckResult:
    check_id: str
    check_version: int
    status: str  # PASS | FAIL | REVIEW | NOTE
    confidence: float
    method: str
    reason: str
    evidence: list[dict] = field(default_factory=list)


@dataclass
class Lead:
    lead_id: str
    retailer: str
    plan_peak_rate_c_per_kwh: float
    crm_email: str
    call_started_at: str  # ISO date
