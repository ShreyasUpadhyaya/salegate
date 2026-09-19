"""Lead review: verdict, timeline strip, checks, transcript, override.

The timeline strip is the one bold element (qa-console-ui skill): a full-width
bar the length of the call, speaker lanes, markers coloured by check status.
Clicking a marker sets the audio start time. Everything else stays quiet.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from ui.api_client import (
    get_overrides,
    get_score,
    get_transcript,
    post_override,
    post_score,
    post_submit,
)
from ui.theme import (
    INK,
    MUTED,
    RULE,
    decision_chip,
    decision_label,
    format_timestamp,
    inject_css,
    status_chip,
    status_colour,
)

st.set_page_config(
    page_title="Lead review | Salegate", page_icon=":material/fact_check:", layout="wide"
)
inject_css()

CRITICAL_STATUS_ORDER = {"FAIL": 0, "REVIEW": 1, "NOTE": 2, "PASS": 3, "NA": 4}


def build_timeline(transcript: dict, results: list[dict], selected_idx: int | None) -> go.Figure:
    """Full-width strip: agent lane above, customer lane below, check markers
    on a middle lane coloured by status. Clicking a marker or a speech bar
    should move the play head; Plotly's own click handling covers that.
    """
    duration = transcript.get("duration_s") or 1.0
    fig = go.Figure()

    lane_y = {"agent": 1.0, "note": 0.5, "customer": 0.0}
    lane_colour = {"agent": MUTED, "customer": MUTED}

    for speaker in ("agent", "customer"):
        turns = [u for u in transcript["utterances"] if u["speaker"] == speaker]
        for turn in turns:
            fig.add_shape(
                type="rect",
                x0=turn["start_s"],
                x1=max(turn["end_s"], turn["start_s"] + 0.3),
                y0=lane_y[speaker] - 0.06,
                y1=lane_y[speaker] + 0.06,
                fillcolor=lane_colour[speaker],
                opacity=0.35,
                line_width=0,
            )

    marker_x, marker_y, marker_colour, marker_text, marker_ids = [], [], [], [], []
    for result in results:
        for evidence in result.get("evidence", []):
            marker_x.append(evidence.get("start_s", 0.0))
            marker_y.append(lane_y["note"])
            colour = status_colour(result.get("effective_status", result["status"]))
            marker_colour.append(colour)
            ts = format_timestamp(evidence.get("start_s", 0.0))
            marker_text.append(f"{result['check_id']} — {result['status']} at {ts}")
            marker_ids.append(result["check_id"])

    fig.add_trace(
        go.Scatter(
            x=marker_x,
            y=marker_y,
            mode="markers",
            marker={"size": 12, "color": marker_colour, "line": {"width": 1, "color": INK}},
            text=marker_text,
            hovertemplate="%{text}<extra></extra>",
            customdata=marker_ids,
            name="checks",
        )
    )

    if selected_idx is not None:
        turn = transcript["utterances"][selected_idx]
        fig.add_vline(x=turn["start_s"], line_color=INK, line_width=2, line_dash="dot")

    fig.update_yaxes(
        range=[-0.3, 1.3],
        tickvals=[0.0, 0.5, 1.0],
        ticktext=["Customer", "Checks", "Agent"],
        showgrid=False,
        zeroline=False,
    )
    fig.update_xaxes(
        title="Seconds into the call",
        range=[0, duration],
        showgrid=True,
        gridcolor=RULE,
        zeroline=False,
    )
    fig.update_layout(
        height=220,
        margin={"l": 10, "r": 10, "t": 10, "b": 40},
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
    )
    return fig


def render_check_row(result: dict) -> None:
    effective = result.get("effective_status", result["status"])
    overridden = effective != result["status"]
    header_cols = st.columns([5, 2])
    with header_cols[0]:
        st.markdown(f"**{result['check_id'].replace('_', ' ')}**", unsafe_allow_html=False)
    with header_cols[1]:
        chip = status_chip(effective)
        if overridden:
            chip += f' <span class="mono">(model said {result["status"]})</span>'
        st.markdown(chip, unsafe_allow_html=True)

    st.caption(result["reason"])

    for evidence in result.get("evidence", []):
        ts = format_timestamp(evidence.get("start_s", 0.0))
        speaker = evidence.get("speaker", "")
        text = evidence.get("text_redacted", "")
        cols = st.columns([1, 8])
        with cols[0]:
            play_key = f"play-{result['check_result_id']}-{evidence.get('utterance_id')}"
            if st.button(f"Play from {ts}", key=play_key):
                st.session_state["play_at"] = evidence.get("start_s", 0.0)
                st.session_state["selected_check"] = result["check_id"]
        with cols[1]:
            line = f'<span class="mono">{ts} {speaker}</span><br>{text}'
            st.markdown(f'<div class="evidence-line">{line}</div>', unsafe_allow_html=True)

    with st.expander("Override this check"):
        auditor = st.text_input("Auditor", key=f"auditor-{result['check_result_id']}")
        new_status = st.selectbox(
            "New status",
            ["PASS", "FAIL", "REVIEW", "NOTE", "NA"],
            key=f"status-{result['check_result_id']}",
        )
        reason = st.text_area("Reason", key=f"reason-{result['check_result_id']}")
        if st.button("Save override", key=f"save-{result['check_result_id']}"):
            if not auditor or not reason:
                st.warning("Auditor and reason are both required.")
            else:
                outcome = post_override(result["check_result_id"], auditor, new_status, reason)
                if outcome is not None:
                    st.success("Override saved.")
                    st.rerun()

        history = get_overrides(result["check_result_id"])
        if history:
            st.markdown('<p class="lead-meta">Override history</p>', unsafe_allow_html=True)
            for entry in history:
                st.markdown(
                    f'<span class="mono">{entry["created_at"][:19]}</span> '
                    f'{entry["auditor"]}: {entry["old_status"]} → {entry["new_status"]} '
                    f'— {entry["reason"]}',
                    unsafe_allow_html=True,
                )


st.title("Lead review")

lead_id = st.text_input("Lead ID", value=st.session_state.get("lead_id", "L-DEMO-1"))
st.session_state["lead_id"] = lead_id

action_cols = st.columns([1, 1, 6])
with action_cols[0]:
    if st.button("Score this lead"):
        result = post_score(lead_id)
        if result is not None:
            st.rerun()
with action_cols[1]:
    if st.button("Submit"):
        result = post_submit(lead_id)
        if result is not None:
            st.success(f"Submitted. {decision_label(result['decision'])}.")

score = get_score(lead_id)
transcript = get_transcript(lead_id)

if score is None:
    st.info(
        "This lead has not been scored yet. Click **Score this lead** above, "
        "or seed one with `uv run python scripts/seed_history.py`."
    )
    st.stop()

def _sort_key(r: dict) -> tuple[int, str]:
    return (CRITICAL_STATUS_ORDER.get(r.get("effective_status", r["status"]), 9), r["check_id"])


results = sorted(score["results"], key=_sort_key)
fails = [r for r in results if r.get("effective_status", r["status"]) == "FAIL"]
reviews = [r for r in results if r.get("effective_status", r["status"]) == "REVIEW"]

if fails:
    verdict = f"Held for TL review. {len(fails)} critical check(s) failed: " + ", ".join(
        r["check_id"].replace("_", " ") for r in fails[:3]
    )
elif reviews:
    verdict = f"Sent to QA review. {len(reviews)} check(s) need a human look."
else:
    verdict = "Cleared every critical check."

st.markdown(f'<p class="verdict-line">{verdict}</p>', unsafe_allow_html=True)
st.markdown(decision_chip(score["decision"]), unsafe_allow_html=True)

st.markdown(
    f'<p class="lead-meta">Lead <span class="mono">{lead_id}</span> · '
    f'Library snapshot <span class="mono">{score["library_snapshot_hash"][:10]}</span> · '
    f'Scored <span class="mono">{score["scored_at"][:19]}</span></p>',
    unsafe_allow_html=True,
)

st.divider()

if transcript and transcript.get("utterances"):
    st.plotly_chart(
        build_timeline(transcript, results, None),
        use_container_width=True,
        config={"displayModeBar": False},
    )
else:
    st.caption("No transcript available for the timeline strip yet.")

st.divider()

col_checks, col_transcript = st.columns([45, 55])

with col_checks:
    st.subheader("Checks")

    if fails:
        st.markdown(f"**Failed, critical** ({len(fails)})")
        for result in fails:
            render_check_row(result)
        st.markdown("---")

    if reviews:
        st.markdown(f"**Needs review** ({len(reviews)})")
        for result in reviews:
            render_check_row(result)
        st.markdown("---")

    passes = [r for r in results if r.get("effective_status", r["status"]) == "PASS"]
    if passes:
        with st.expander(f"Passed ({len(passes)})"):
            for result in passes:
                render_check_row(result)

    notes = [r for r in results if r.get("effective_status", r["status"]) == "NOTE"]
    if notes:
        with st.expander(f"Coaching notes ({len(notes)})"):
            for result in notes:
                st.markdown(f"**{result['check_id'].replace('_', ' ')}**")
                st.caption(result["reason"])

with col_transcript:
    st.subheader("Transcript")
    if transcript and transcript.get("utterances"):
        play_at = st.session_state.get("play_at")
        if transcript.get("audio_path"):
            try:
                st.audio(transcript["audio_path"], start_time=int(play_at or 0))
            except Exception:
                st.caption("Audio file not reachable from this machine.")
        for utterance in transcript["utterances"]:
            is_selected = (
                play_at is not None and abs(utterance["start_s"] - play_at) < 0.01
            )
            css_class = "evidence-line selected" if is_selected else "evidence-line"
            ts = format_timestamp(utterance["start_s"])
            st.markdown(
                f'<div class="{css_class}"><span class="mono">{ts} {utterance["speaker"]}</span>'
                f'<br>{utterance["text_redacted"]}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No transcript yet.")
