"""Salegate console. An audit ledger for listening, not a marketing dashboard."""

from __future__ import annotations

import streamlit as st

from ui.theme import inject_css

st.set_page_config(page_title="Salegate", page_icon=":material/fact_check:", layout="wide")
inject_css()

st.title("Salegate")
st.markdown(
    "Every sale is scored against its retailer checklist before it can submit. "
    "Green goes through, red is held with the failing check, transcript line and audio timestamp."
)

st.markdown("### Where to go")
st.markdown(
    "- **Lead review** — pick a lead, hear the call, see every check and its evidence.\n"
    "- **Queues** — leads held for TL, sent to QA review, or auto submitted.\n"
    "- **Dashboards** — agent rollups, first pass yield, critical fail rate."
)

st.markdown(
    '<p class="lead-meta">Seeded demo data is labelled where it appears. '
    "The two calls in this build are self-recorded (D17), synthetic customers.</p>",
    unsafe_allow_html=True,
)
