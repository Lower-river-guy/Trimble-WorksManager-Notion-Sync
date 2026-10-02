"""Runtime configuration for Trimble WorksManager → Notion sync."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _read_version() -> str:
    version_file = Path(__file__).resolve().parent / "VERSION"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    return os.getenv("APP_VERSION", "0.01.00")


@dataclass(frozen=True)
class Settings:
    version: str
    google_cloud_project: str
    dry_run: bool
    log_level: str

    trimble_base_url: str
    trimble_token_url: str
    trimble_scope: str
    trimble_account_trn: str
    trimble_timeout: int

    notion_api_version: str
    notion_token: str | None

    projects_database_id: str
    projects_data_source_id: str
    devices_database_id: str
    devices_data_source_id: str
    machines_database_id: str
    machines_data_source_id: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            version=_read_version(),
            google_cloud_project=os.getenv(
                "GOOGLE_CLOUD_PROJECT", "work-projects-486912"
            ),
            dry_run=_env_bool("DRY_RUN", True),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            trimble_base_url=os.getenv(
                "TRIMBLE_BASE_URL",
                "https://cloud.api.trimble.com/site-management/v1/",
            ),
            trimble_token_url=os.getenv(
                "TRIMBLE_TOKEN_URL", "https://id.trimble.com/oauth/token"
            ),
            trimble_scope=os.getenv("TRIMBLE_SCOPE", "site-management"),
            trimble_account_trn=os.getenv(
                "TRIMBLE_ACCOUNT_TRN",
                "trn::profilex:us-west-2:account:f692acbd-fd57-4f54-a0df-b754d7e85028",
            ),
            trimble_timeout=int(os.getenv("TRIMBLE_TIMEOUT", "45")),
            notion_api_version=os.getenv("NOTION_API_VERSION", "2025-09-03"),
            notion_token=(
                os.getenv("NOTION_TOKEN")
                or os.getenv("NOTION_API_KEY")
                or os.getenv("NOTION_API_TOKEN")
            ),
            projects_database_id=os.getenv(
                "NOTION_PROJECTS_DATABASE_ID",
                "3ec284decb43807e92a2f92a141c251b",
            ),
            projects_data_source_id=os.getenv(
                "NOTION_PROJECTS_DATA_SOURCE_ID",
                "3ec284de-cb43-8019-a0bc-000b0babfe2e",
            ),
            devices_database_id=os.getenv(
                "NOTION_DEVICES_DATABASE_ID",
                "3ec284decb43806eabd3f67b320e640b",
            ),
            devices_data_source_id=os.getenv(
                "NOTION_DEVICES_DATA_SOURCE_ID",
                "3ec284de-cb43-805f-ad31-000b10b54520",
            ),
            machines_database_id=os.getenv(
                "NOTION_MACHINES_DATABASE_ID",
                "3ec284decb438041b445f834df6de002",
            ),
            machines_data_source_id=os.getenv(
                "NOTION_MACHINES_DATA_SOURCE_ID",
                "3ec284de-cb43-806a-a745-000bac242477",
            ),
        )
