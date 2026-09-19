"""Dashboards: agent rollup with first pass yield and critical fail rate."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.api_client import get_agent_rollup
from ui.theme import FAIL, PASS, inject_css

st.set_page_config(
    page_title="Dashboards | Salegate", page_icon=":material/monitoring:", layout="wide"
)
inject_css()

st.title("Dashboards")
st.markdown(
    '<p class="lead-meta">Seeded demo data. Run '
    '<code>uv run python scripts/seed_history.py</code> to generate it (DECISIONS D12).</p>',
    unsafe_allow_html=True,
)

rows = get_agent_rollup()

if not rows:
    st.info("No scored history yet. Run `uv run python scripts/seed_history.py`.")
    st.stop()

df = pd.DataFrame(rows)
df = df.rename(
    columns={
        "agent_id": "Agent",
        "total_scored": "Scored",
        "auto_submit": "Auto submitted",
        "qa_review": "QA review",
        "held_tl": "Held for TL",
        "first_pass_yield": "First pass yield",
        "critical_fail_rate": "Critical fail rate",
    }
)

st.subheader("By agent")
st.dataframe(
    df.style.format({"First pass yield": "{:.0%}", "Critical fail rate": "{:.0%}"}),
    width="stretch",
    hide_index=True,
)

st.divider()

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("First pass yield by agent")
    fig = px.bar(df, x="Agent", y="First pass yield", color_discrete_sequence=[PASS])
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    fig.update_layout(showlegend=False, margin={"l": 10, "r": 10, "t": 10, "b": 10}, height=320)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

with col_b:
    st.subheader("Critical fail rate by agent")
    fig = px.bar(df, x="Agent", y="Critical fail rate", color_discrete_sequence=[FAIL])
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    fig.update_layout(showlegend=False, margin={"l": 10, "r": 10, "t": 10, "b": 10}, height=320)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
