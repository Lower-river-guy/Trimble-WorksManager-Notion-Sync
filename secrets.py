"""Resolve credentials from environment and Google Secret Manager."""

from __future__ import annotations

import os
from typing import Iterable

from google.cloud import secretmanager


def _sm_client() -> secretmanager.SecretManagerServiceClient:
    return secretmanager.SecretManagerServiceClient()


def access_secret_version(name: str) -> str:
    client = _sm_client()
    response = client.access_secret_version(name=name)
    return response.payload.data.decode("UTF-8")


def resolve_secret_value(
    env: dict[str, str],
    key: str,
    *,
    project_id: str,
    aliases: Iterable[str] | None = None,
) -> str:
    """Resolve a secret from env value or Secret Manager short name."""
    raw = (env.get(key) or "").strip()
    if raw and not raw.startswith("projects/"):
        return raw
    if raw.startswith("projects/"):
        return access_secret_version(raw)

    names = [key]
    if aliases:
        names.extend(aliases)

    client = _sm_client()
    for secret_name in names:
        resource = (
            f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        )
        try:
            response = client.access_secret_version(name=resource)
            return response.payload.data.decode("UTF-8").strip()
        except Exception:
            continue

    raise RuntimeError(
        f"Could not resolve secret for {key}. "
        f"Set {key} in the environment or create Secret Manager secret."
    )


def hydrate_credentials(env: dict[str, str], project_id: str) -> dict[str, str]:
    """Return env with Trimble and Notion credentials resolved."""
    out = dict(env)
    out["TRIMBLE_CLIENT_ID"] = resolve_secret_value(
        out,
        "TRIMBLE_CLIENT_ID",
        project_id=project_id,
    )
    out["TRIMBLE_CLIENT_SECRET"] = resolve_secret_value(
        out,
        "TRIMBLE_CLIENT_SECRET",
        project_id=project_id,
    )
    notion = (
        out.get("NOTION_TOKEN")
        or out.get("NOTION_API_KEY")
        or out.get("NOTION_API_TOKEN")
    )
    if not notion or str(notion).startswith("projects/"):
        out["NOTION_TOKEN"] = resolve_secret_value(
            out,
            "NOTION_TOKEN",
            project_id=project_id,
            aliases=(
                "Notion_Google_Cloud_Sync",
                "NOTION_API_KEY",
                "NOTion_Google_Cloud_Sync",
            ),
        )
    else:
        out["NOTION_TOKEN"] = str(notion).strip()
    return out
