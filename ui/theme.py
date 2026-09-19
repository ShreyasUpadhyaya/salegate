"""Design tokens and the one injected CSS block, per the qa-console-ui skill.

.streamlit/config.toml sets the base theme (background, text, border, radius).
This module adds what config.toml cannot: the status colours, monospace
timestamps, and chip styling, plus small helpers so pages do not repeat
inline HTML for the same three things (status chip, decision chip, mono text).
"""

from __future__ import annotations

import streamlit as st

# Status colours. Always paired with a word in the UI, never colour alone
# (skill: "Status shown by colour only" is banned).
PASS = "#1E7A4C"
FAIL = "#B3261E"
REVIEW = "#A15C07"
NOTE = "#4B5B75"
LINK = "#2B5AA8"

INK = "#1C2430"
MUTED = "#5B6573"
LEDGER = "#F6F7F4"
SHEET = "#FFFFFF"
RULE = "#D6DBD3"

_STATUS_COLOURS = {
    "PASS": PASS,
    "FAIL": FAIL,
    "REVIEW": REVIEW,
    "NOTE": NOTE,
    "NA": MUTED,
}
_STATUS_LABELS = {
    "PASS": "Passed",
    "FAIL": "Failed",
    "REVIEW": "Needs review",
    "NOTE": "Note",
    "NA": "Not applicable",
}

_DECISION_COLOURS = {
    "AUTO_SUBMIT": PASS,
    "QA_REVIEW": REVIEW,
    "HELD_TL": FAIL,
}
_DECISION_LABELS = {
    "AUTO_SUBMIT": "Auto submitted",
    "QA_REVIEW": "Sent to QA review",
    "HELD_TL": "Held for TL review",
}


def inject_css() -> None:
    """One CSS block: mono timestamps, chip shape, no shadows. Call once per page."""
    st.markdown(
        f"""
        <style>
        .mono {{
            font-family: "IBM Plex Mono", ui-monospace, monospace;
            font-variant-numeric: tabular-nums;
            color: {MUTED};
        }}
        .status-chip {{
            display: inline-block;
            padding: 2px 10px;
            border-radius: 3px;
            font-size: 0.85rem;
            font-weight: 600;
            border: 1px solid transparent;
        }}
        .decision-chip {{
            display: inline-block;
            padding: 4px 14px;
            border-radius: 3px;
            font-size: 0.95rem;
            font-weight: 700;
        }}
        .sheet-panel {{
            background: {SHEET};
            border: 1px solid {RULE};
            border-radius: 6px;
            padding: 1rem;
        }}
        .verdict-line {{
            font-size: 1.15rem;
            color: {INK};
            margin-bottom: 0.25rem;
        }}
        .lead-meta {{
            color: {MUTED};
            font-size: 0.9rem;
        }}
        .evidence-line {{
            border-left: 3px solid {RULE};
            padding-left: 10px;
            margin: 4px 0;
        }}
        .evidence-line.selected {{
            border-left-color: {LINK};
            background: rgba(43, 90, 168, 0.06);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_chip(status: str) -> str:
    """Small HTML chip: colour and word together, never colour alone."""
    colour = _STATUS_COLOURS.get(status, MUTED)
    label = _STATUS_LABELS.get(status, status)
    return (
        f'<span class="status-chip" style="background:{colour}1a;'
        f'color:{colour};border-color:{colour}55">{label}</span>'
    )


def decision_chip(decision: str) -> str:
    colour = _DECISION_COLOURS.get(decision, MUTED)
    label = _DECISION_LABELS.get(decision, decision)
    style = f"background:{colour}1a;color:{colour}"
    return f'<span class="decision-chip" style="{style}">{label}</span>'


def decision_label(decision: str) -> str:
    return _DECISION_LABELS.get(decision, decision)


def mono(text: str) -> str:
    return f'<span class="mono">{text}</span>'


def status_colour(status: str) -> str:
    return _STATUS_COLOURS.get(status, MUTED)


def format_timestamp(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"
