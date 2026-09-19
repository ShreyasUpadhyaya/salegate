"""Thin httpx wrapper for the FastAPI backend. No business logic here.

Uses 127.0.0.1 per CLAUDE.md, not localhost.
"""

from __future__ import annotations

from functools import lru_cache

import httpx
import streamlit as st

API_BASE = "http://127.0.0.1:8000"


@lru_cache(maxsize=1)
def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=10.0)


def get_leads() -> list[dict]:
    """All leads. There is no list-leads endpoint yet, so this reads the
    dashboard rollup for agent ids and falls back to an empty list; the lead
    picker also accepts a typed lead id, which always works.
    """
    try:
        response = _client().get("/api/dashboards/agents")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return []


def get_score(lead_id: str) -> dict | None:
    try:
        response = _client().get(f"/api/leads/{lead_id}/score")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        st.error(f"Could not reach the API: {exc}")
        return None


def post_score(lead_id: str) -> dict | None:
    try:
        response = _client().post(f"/api/leads/{lead_id}/score")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        st.error(f"Scoring failed: {exc.response.json().get('detail', exc)}")
        return None
    except httpx.HTTPError as exc:
        st.error(f"Could not reach the API: {exc}")
        return None


def post_submit(lead_id: str) -> dict | None:
    try:
        response = _client().post(f"/api/leads/{lead_id}/submit")
        if response.status_code == 409:
            st.warning(response.json().get("detail", "Cannot submit yet."))
            return None
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        st.error(f"Could not reach the API: {exc}")
        return None


def post_override(check_result_id: int, auditor: str, new_status: str, reason: str) -> dict | None:
    try:
        response = _client().post(
            f"/api/check-results/{check_result_id}/override",
            json={"auditor": auditor, "new_status": new_status, "reason": reason},
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        st.error(f"Override failed: {exc.response.json().get('detail', exc)}")
        return None
    except httpx.HTTPError as exc:
        st.error(f"Could not reach the API: {exc}")
        return None


def get_overrides(check_result_id: int) -> list[dict]:
    try:
        response = _client().get(f"/api/check-results/{check_result_id}/overrides")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return []


def get_transcript(lead_id: str) -> dict | None:
    try:
        response = _client().get(f"/api/leads/{lead_id}/transcript")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        st.error(f"Could not reach the API: {exc}")
        return None


def get_agent_rollup() -> list[dict]:
    try:
        response = _client().get("/api/dashboards/agents")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return []
