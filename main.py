#!/usr/bin/env python3
"""Trimble WorksManager → Notion sync (Cloud Run Job)."""

from __future__ import annotations

import logging
import os
import sys

from config import Settings
from log_utils import log
from notion_client import NotionClient
from gcp_secrets import hydrate_credentials
from sync_engine import SyncEngine
from trimble_client import TrimbleClient

BANNER = "><(((º>            ><(((º>          RK               ><(((º>"


def print_summary(summary, *, dry_run: bool) -> None:
    mode = "DRY_RUN" if dry_run else "APPLY"
    log("SUMMARY", f"Mode={mode}")
    log("SUMMARY", f"Trimble projects={summary.trimble_projects}")
    log("SUMMARY", f"Trimble devices={summary.trimble_devices}")
    log("SUMMARY", f"Trimble machines={summary.trimble_machines}")
    log(
        "SUMMARY",
        f"Trimble devices with project assignment={summary.trimble_devices_assigned}",
    )

    for label, stats in (
        ("Notion Projects", summary.projects),
        ("Notion Devices", summary.devices),
        ("Notion Machines", summary.machines),
    ):
        log(
            "SUMMARY",
            f"{label}: created={stats.created} updated={stats.updated} "
            f"unchanged={stats.unchanged} errors={stats.errors}",
        )

    if summary.warnings:
        log("WARNING", f"{len(summary.warnings)} item-level issues logged")


def main() -> int:
    print(BANNER)
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(message)s",
    )

    log("VERSION", settings.version)
    log("MODE", "DRY_RUN" if settings.dry_run else "APPLY")

    env = hydrate_credentials(dict(os.environ), settings.google_cloud_project)
    notion_token = env.get("NOTION_TOKEN")
    if not notion_token:
        log("ERROR", "NOTION_TOKEN could not be resolved")
        return 2

    trimble = TrimbleClient(
        client_id=env["TRIMBLE_CLIENT_ID"],
        client_secret=env["TRIMBLE_CLIENT_SECRET"],
        base_url=settings.trimble_base_url,
        token_url=settings.trimble_token_url,
        scope=settings.trimble_scope,
        account_trn=settings.trimble_account_trn,
        timeout=settings.trimble_timeout,
    )

    try:
        trimble.authenticate()
    except Exception as exc:
        log("ERROR", f"Trimble authentication failed: {exc}")
        return 1

    try:
        snapshot = trimble.fetch_snapshot()
    except Exception as exc:
        log("ERROR", f"Trimble read failed: {exc}")
        return 1

    notion = NotionClient(notion_token, api_version=settings.notion_api_version)
    try:
        log(
            "NOTION",
            f"Projects target: {notion.verify_data_source(settings.projects_data_source_id)}",
        )
        log(
            "NOTION",
            f"Devices target: {notion.verify_data_source(settings.devices_data_source_id)}",
        )
        log(
            "NOTION",
            f"Machines target: {notion.verify_data_source(settings.machines_data_source_id)}",
        )
    except Exception as exc:
        log("ERROR", f"Notion target verification failed: {exc}")
        return 1

    engine = SyncEngine(
        notion,
        projects_ds=settings.projects_data_source_id,
        devices_ds=settings.devices_data_source_id,
        machines_ds=settings.machines_data_source_id,
        dry_run=settings.dry_run,
    )

    try:
        summary = engine.run(snapshot)
    except Exception as exc:
        log("ERROR", f"Sync failed: {exc}")
        return 1

    print_summary(summary, dry_run=settings.dry_run)
    total_errors = (
        summary.projects.errors + summary.devices.errors + summary.machines.errors
    )
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
