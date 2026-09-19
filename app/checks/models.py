"""Shapes evaluators take and return. No DB access here, see CLAUDE.md."""

from __future__ import annotations

from typing import Any, TypedDict


class TurnDict(TypedDict, total=False):
    """One utterance as evaluators see it. Matches app.models.Utterance fields."""

    idx: int
    speaker: str
    start_s: float
    end_s: float
    text_redacted: str
    avg_confidence: float
    speaker_source: str


class CheckResultDict(TypedDict):
    """The evidence contract from PLAN.md. A PASS with empty evidence is a bug."""

    check_id: str
    check_version: int
    status: str  # PASS | FAIL | REVIEW | NOTE | NA
    confidence: float
    method: str  # fuzzy | regex | extract | timing | llm
    reason: str
    evidence: list[dict[str, Any]]
