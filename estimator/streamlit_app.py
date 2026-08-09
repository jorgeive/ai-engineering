"""Streamlit client for session-aware transcript estimation."""

from __future__ import annotations

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("ESTIMATOR_API_BASE_URL", "http://localhost:8000").rstrip("/")
SESSIONS_ENDPOINT = f"{API_BASE_URL}/sessions"

st.set_page_config(page_title="Software Estimator", page_icon="📊")
st.title("Software Estimator")
st.caption(
    "Each page gets an in-memory session. Supporting documents are extracted by "
    "the service and added to the transcript before estimation."
)


def create_session() -> str:
    response = httpx.post(SESSIONS_ENDPOINT, timeout=httpx.Timeout(10.0, connect=5.0))
    response.raise_for_status()
    return response.json()["session_id"]


def refresh_metadata() -> None:
    response = httpx.get(
        f"{SESSIONS_ENDPOINT}/{st.session_state.session_id}",
        timeout=httpx.Timeout(10.0, connect=5.0),
    )
    response.raise_for_status()
    st.session_state.project_metadata = response.json()["project_metadata"]


if "session_id" not in st.session_state:
    try:
        st.session_state.session_id = create_session()
        st.session_state.project_metadata = {}
    except httpx.HTTPError as exc:
        st.error(f"Could not create a session at `{SESSIONS_ENDPOINT}`: {exc}")
        st.stop()

session_estimate_endpoint = f"{SESSIONS_ENDPOINT}/{st.session_state.session_id}/estimate"

with st.form("estimation_form", clear_on_submit=False):
    transcript = st.text_area(
        "Transcript",
        height=240,
        placeholder="Paste the meeting transcript here...",
        help="The transcript must contain at least 20 characters.",
    )
    attachments = st.file_uploader(
        "Supporting documentation",
        accept_multiple_files=True,
        type=["txt", "md", "csv", "json", "yaml", "yml", "xml", "pdf", "docx"],
    )
    submitted = st.form_submit_button("Generate estimation", type="primary")

if submitted:
    if len(transcript.strip()) < 20:
        st.error("The transcript must be at least 20 characters long.")
    else:
        files = [
            (
                "attachments",
                (file.name, file.getvalue(), file.type or "application/octet-stream"),
            )
            for file in attachments or []
        ]
        with st.spinner("Calling the estimator service…"):
            try:
                response = httpx.post(
                    session_estimate_endpoint,
                    data={"transcript": transcript.strip()},
                    files=files or None,
                    timeout=httpx.Timeout(120.0, connect=10.0),
                )
                response.raise_for_status()
                body = response.json()
            except httpx.HTTPStatusError as exc:
                st.error(f"Service returned {exc.response.status_code}: {exc.response.text}")
            except httpx.HTTPError as exc:
                st.error(f"Could not reach the estimator service: {exc}")
            else:
                st.json(body)
                try:
                    refresh_metadata()
                except httpx.HTTPError as exc:
                    st.warning(f"Could not refresh session metadata: {exc}")

with st.sidebar:
    st.header("Session")
    st.code(session_estimate_endpoint, language="text")
    st.caption(f"Session ID: `{st.session_state.session_id}`")
    with st.expander("Current project metadata", expanded=True):
        st.json(st.session_state.get("project_metadata", {}))
    if st.button("Nueva conversación"):
        try:
            st.session_state.session_id = create_session()
            st.session_state.project_metadata = {}
            st.rerun()
        except httpx.HTTPError as exc:
            st.error(f"Could not create a new session: {exc}")
