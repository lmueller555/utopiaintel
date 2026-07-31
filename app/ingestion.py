"""Validation, lightweight metadata parsing, and intel persistence."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from app.database import IntelSubmission


class IngestionError(ValueError):
    """Raised when an intel payload cannot be accepted."""


@dataclass(frozen=True)
class SubmissionPayload:
    source_url: str
    submitter_province: str
    raw_html: str
    plain_text: str
    intel_type: str = "unknown"
    target_province: str = "Unknown"
    target_kingdom: str = "Unknown"

    @classmethod
    def from_mapping(cls, data) -> "SubmissionPayload":
        return cls(
            source_url=str(data.get("source_url") or data.get("url") or "").strip(),
            submitter_province=str(
                data.get("submitter_province") or data.get("prov") or ""
            ).strip(),
            raw_html=str(data.get("raw_html") or data.get("data_html") or ""),
            plain_text=str(data.get("plain_text") or data.get("data_simple") or ""),
            intel_type=str(data.get("intel_type") or "unknown").strip().lower(),
            target_province=str(data.get("target_province") or "Unknown").strip(),
            target_kingdom=str(data.get("target_kingdom") or "Unknown").strip(),
        )


def validate_payload(payload: SubmissionPayload, max_payload_bytes: int) -> None:
    if not payload.source_url:
        raise IngestionError("A source URL is required.")
    parsed_url = urlparse(payload.source_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise IngestionError("The source URL must be an absolute HTTP(S) URL.")
    if not payload.submitter_province:
        raise IngestionError("The submitting province is required.")
    if not payload.raw_html and not payload.plain_text:
        raise IngestionError("Raw HTML or plain-text intel is required.")
    size = len(payload.raw_html.encode()) + len(payload.plain_text.encode())
    if size > max_payload_bytes:
        raise IngestionError(f"The intel payload exceeds {max_payload_bytes} bytes.")


def enrich_payload(payload: SubmissionPayload) -> SubmissionPayload:
    """Infer a few display fields while preserving the original submission."""
    text = payload.plain_text
    target_province = payload.target_province
    target_kingdom = payload.target_kingdom
    intel_type = payload.intel_type

    if target_province == "Unknown":
        match = re.search(r"(?:The )?Province of ([^\n(]+)", text, re.IGNORECASE)
        if match:
            target_province = match.group(1).strip()
    if target_kingdom == "Unknown":
        match = re.search(r"\((\d+\s*:\s*\d+)\)", text)
        if match:
            target_kingdom = match.group(1).replace(" ", "")
    if intel_type == "unknown":
        lowered = text.lower()
        for candidate, markers in {
            "survey": ("survey", "buildings report"),
            "spy on throne": ("spy on throne", "throne page"),
            "spy on military": ("spy on military", "military affairs"),
        }.items():
            if any(marker in lowered for marker in markers):
                intel_type = candidate
                break

    return SubmissionPayload(
        source_url=payload.source_url,
        submitter_province=payload.submitter_province,
        raw_html=payload.raw_html,
        plain_text=payload.plain_text,
        intel_type=intel_type,
        target_province=target_province,
        target_kingdom=target_kingdom,
    )


def ingest(session, payload: SubmissionPayload, max_payload_bytes: int) -> IntelSubmission:
    validate_payload(payload, max_payload_bytes)
    payload = enrich_payload(payload)
    digest = hashlib.sha256(
        (payload.source_url + "\0" + payload.raw_html + "\0" + payload.plain_text).encode()
    ).hexdigest()
    submission = IntelSubmission(
        id=str(uuid.uuid4()),
        source_url=payload.source_url,
        submitter_province=payload.submitter_province[:160],
        intel_type=payload.intel_type[:80],
        target_province=payload.target_province[:160],
        target_kingdom=payload.target_kingdom[:32],
        raw_html=payload.raw_html,
        plain_text=payload.plain_text,
        payload_hash=digest,
        parser_status="metadata_parsed",
    )
    session.add(submission)
    session.flush()
    return submission

