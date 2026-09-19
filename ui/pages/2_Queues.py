"""Queues: leads grouped by gate decision. Held first, since that is the work."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# streamlit run puts this file's own directory on sys.path, not the project
# root, so `ui.api_client` and `ui.theme` do not resolve on their own.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ui.api_client import get_agent_rollup  # noqa: E402
from ui.theme import decision_chip, inject_css  # noqa: E402

st.set_page_config(page_title="Queues | Salegate", page_icon=":material/inbox:", layout="wide")
inject_css()

st.title("Queues")
st.caption(
    "There is no list-all-leads endpoint yet, so this page shows the agent rollup "
    "and points you at Lead review to open a specific lead by id."
)

rows = get_agent_rollup()

if not rows:
    st.info("No sales waiting. New calls appear here within minutes of hangup.")
    st.stop()

total_held = sum(r["held_tl"] for r in rows)
total_qa = sum(r["qa_review"] for r in rows)
total_auto = sum(r["auto_submit"] for r in rows)

st.markdown(
    f"{decision_chip('HELD_TL')} **{total_held}** &nbsp;&nbsp; "
    f"{decision_chip('QA_REVIEW')} **{total_qa}** &nbsp;&nbsp; "
    f"{decision_chip('AUTO_SUBMIT')} **{total_auto}**",
    unsafe_allow_html=True,
)

st.divider()
st.subheader("By agent")

for row in sorted(rows, key=lambda r: -r["held_tl"]):
    with st.container(border=True):
        cols = st.columns([2, 1, 1, 1, 2])
        cols[0].markdown(f"**{row['agent_id']}**")
        cols[1].markdown(f"{decision_chip('HELD_TL')} {row['held_tl']}", unsafe_allow_html=True)
        cols[2].markdown(f"{decision_chip('QA_REVIEW')} {row['qa_review']}", unsafe_allow_html=True)
        auto_chip = f"{decision_chip('AUTO_SUBMIT')} {row['auto_submit']}"
        cols[3].markdown(auto_chip, unsafe_allow_html=True)
        fpy = row["first_pass_yield"] * 100
        cfr = row["critical_fail_rate"] * 100
        cols[4].caption(f"First pass yield {fpy:.0f}% · Critical fail rate {cfr:.0f}%")

st.divider()
st.caption("Open **Lead review** from the sidebar to look at a specific lead.")
