"""Streamlit client for the estimation service contract."""

from __future__ import annotations

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("ESTIMATOR_API_BASE_URL", "http://localhost:8000")
ESTIMATE_ENDPOINT = f"{API_BASE_URL.rstrip('/')}/api/v1/estimate"

PROJECT_TYPES = {
    "Mobile app": "mobile_app",
    "Web SaaS": "web_saas",
    "Internal tool": "internal_tool",
    "Data pipeline": "data_pipeline",
}
DETAIL_LEVELS = {
    "Summary": "summary",
    "Medium": "medium",
    "Detailed": "detailed",
}
OUTPUT_FORMATS = {
    "Phases table": "phases_table",
    "Line items": "line_items",
    "Narrative": "narrative",
}

st.set_page_config(page_title="Software Estimator", page_icon="📊")
st.title("Software Estimator")
st.caption("Complete the project brief to request an estimation.")

with st.form("estimation_form"):
    description = st.text_area(
        "Project description",
        placeholder="Describe the project, its goals, users, and main requirements...",
        max_chars=2000,
        height=180,
    )
    project_type_label = st.selectbox("Project type", list(PROJECT_TYPES))
    detail_level_label = st.selectbox("Detail level", list(DETAIL_LEVELS))
    output_format_label = st.selectbox("Output format", list(OUTPUT_FORMATS))
    submitted = st.form_submit_button("Generate estimation", type="primary")

if submitted:
    if len(description.strip()) < 20:
        st.error("The project description must contain at least 20 characters.")
    else:
        payload = {
            "description": description.strip(),
            "project_type": PROJECT_TYPES[project_type_label],
            "detail_level": DETAIL_LEVELS[detail_level_label],
            "output_format": OUTPUT_FORMATS[output_format_label],
        }
        try:
            response = httpx.post(ESTIMATE_ENDPOINT, json=payload, timeout=120.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            st.error(f"The estimator rejected the request ({exc.response.status_code}).")
        except httpx.RequestError as exc:
            st.error(f"Could not reach the estimator at {ESTIMATE_ENDPOINT}: {exc}")
        else:
            result = response.json()
            st.subheader("Estimation")
            st.markdown(result["text"])
            st.caption(f"Prompt version: {result['prompt_version']}")

with st.sidebar:
    st.header("Service")
    st.code(ESTIMATE_ENDPOINT, language="text")
