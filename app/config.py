"""Runtime configuration shared by Flask and Streamlit."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


def _secret(secrets: Mapping[str, Any] | None, name: str, default: str) -> str:
    if secrets is not None and name in secrets:
        return str(secrets[name])
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    database_url: str
    ingestion_api_key: str
    max_payload_bytes: int
    allowed_origins: tuple[str, ...] = (
        "https://utopia-game.com",
        "https://www.utopia-game.com",
    )

    @classmethod
    def load(cls, secrets: Mapping[str, Any] | None = None) -> "Settings":
        database_url = _secret(secrets, "DATABASE_URL", "sqlite:///utopiaintel.db")
        # Some providers still emit the old postgres:// scheme.
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

        return cls(
            database_url=database_url,
            ingestion_api_key=_secret(secrets, "INGESTION_API_KEY", "change-me"),
            max_payload_bytes=int(
                _secret(secrets, "MAX_PAYLOAD_BYTES", str(1024 * 1024))
            ),
            allowed_origins=tuple(
                origin.strip().rstrip("/")
                for origin in _secret(
                    secrets,
                    "ALLOWED_ORIGINS",
                    "https://utopia-game.com,https://www.utopia-game.com",
                ).split(",")
                if origin.strip()
            ),
        )
