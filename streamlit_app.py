"""Streamlit dashboard for submitting and reviewing captured intel."""

from __future__ import annotations

import hmac

import streamlit as st
from sqlalchemy import func, select

from app.config import Settings
from app.database import (
    IntelSubmission,
    initialize_database,
    make_engine,
    make_session_factory,
    session_scope,
)
from app.ingestion import IngestionError, SubmissionPayload, ingest


st.set_page_config(page_title="Utopia Intel", page_icon="🛡️", layout="wide")


@st.cache_resource
def database(settings: Settings):
    engine = make_engine(settings.database_url)
    initialize_database(engine)
    return make_session_factory(engine)


def load_settings() -> Settings:
    try:
        return Settings.load(st.secrets)
    except FileNotFoundError:
        return Settings.load()


settings = load_settings()
session_factory = database(settings)

st.title("🛡️ Utopia Intel")
st.caption("Capture, verify, and review kingdom intel in one shared data store.")

if settings.database_url.startswith("sqlite"):
    st.warning(
        "Using local SQLite storage. Configure DATABASE_URL with PostgreSQL before "
        "using this deployment for durable shared intel."
    )
if settings.ingestion_api_key == "change-me":
    st.error(
        "The default ingestion key is active. Set INGESTION_API_KEY to a long random "
        "secret before sharing this application."
    )

with st.sidebar:
    st.header("Capture intel")
    with st.form("capture_form", clear_on_submit=True):
        api_key = st.text_input("Ingestion key", type="password")
        submitter = st.text_input("Your province")
        source_url = st.text_input("Source URL", value="https://utopia-game.com/")
        intel_type = st.selectbox(
            "Intel type", ["unknown", "survey", "spy on throne", "spy on military", "other"]
        )
        target = st.text_input("Target province (optional)")
        kingdom = st.text_input("Target kingdom (optional)", placeholder="1:2")
        plain_text = st.text_area("Paste captured intel", height=220)
        submitted = st.form_submit_button("Store intel", type="primary", use_container_width=True)

    if submitted:
        if not hmac.compare_digest(api_key, settings.ingestion_api_key):
            st.error("Invalid ingestion key.")
        else:
            try:
                payload = SubmissionPayload(
                    source_url=source_url,
                    submitter_province=submitter,
                    raw_html="",
                    plain_text=plain_text,
                    intel_type=intel_type,
                    target_province=target or "Unknown",
                    target_kingdom=kingdom or "Unknown",
                )
                with session_scope(session_factory) as session:
                    submission = ingest(session, payload, settings.max_payload_bytes)
                st.success(f"Stored submission {submission.id[:8]}…")
            except IngestionError as exc:
                st.error(str(exc))

with session_scope(session_factory) as session:
    total = session.scalar(select(func.count()).select_from(IntelSubmission)) or 0
    targets = session.scalar(
        select(func.count(func.distinct(IntelSubmission.target_province))).where(
            IntelSubmission.target_province != "Unknown"
        )
    ) or 0
    submitters = session.scalar(
        select(func.count(func.distinct(IntelSubmission.submitter_province)))
    ) or 0
    rows = list(
        session.scalars(
            select(IntelSubmission).order_by(IntelSubmission.received_at.desc()).limit(100)
        )
    )
    counts = session.execute(
        select(IntelSubmission.intel_type, func.count(IntelSubmission.id))
        .group_by(IntelSubmission.intel_type)
        .order_by(func.count(IntelSubmission.id).desc())
    ).all()

metric_columns = st.columns(3)
metric_columns[0].metric("Intel submissions", total)
metric_columns[1].metric("Known targets", targets)
metric_columns[2].metric("Contributors", submitters)

chart_column, status_column = st.columns([2, 1])
with chart_column:
    st.subheader("Captured intel by type")
    if counts:
        st.bar_chart(
            [{"Intel type": intel_type, "Submissions": count} for intel_type, count in counts],
            x="Intel type",
            y="Submissions",
        )
    else:
        st.info("No intel has arrived yet. Use the capture form to verify the connection.")
with status_column:
    st.subheader("Connection status")
    st.success("Database connected")
    st.write("The dashboard and Flask API share this data store.")

st.subheader("Recent submissions")
if rows:
    st.dataframe(
        [
            {
                "Received": row.received_at,
                "Type": row.intel_type,
                "Target": row.target_province,
                "Kingdom": row.target_kingdom,
                "Submitted by": row.submitter_province,
                "Status": row.parser_status,
            }
            for row in rows
        ],
        use_container_width=True,
        hide_index=True,
    )
    selected_id = st.selectbox(
        "Inspect a stored submission",
        options=[row.id for row in rows],
        format_func=lambda value: next(
            f"{row.target_province} · {row.intel_type} · {row.received_at:%Y-%m-%d %H:%M UTC}"
            for row in rows
            if row.id == value
        ),
    )
    selected = next(row for row in rows if row.id == selected_id)
    with st.expander("Stored plain-text payload"):
        st.code(selected.plain_text or "(No plain text supplied)", language=None)
else:
    st.info("Recent submissions will appear here after the first successful capture.")
