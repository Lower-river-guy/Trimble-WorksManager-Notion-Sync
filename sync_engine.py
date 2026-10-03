"""Notion upsert engine for Trimble WorksManager snapshot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from log_utils import log
from mapping import design_summary, extract_project_number, iso_now
from notion_client import NotionClient, run_with_notion_errors
from notion_props import date_prop, number, properties_equal, rich_text, title
from trimble_client import DeviceRecord, MachineRecord, ProjectRecord, TrimbleSnapshot


PROJECT_KEYS: tuple[str, ...] = (
    "Name",
    "Trimble Project ID",
    "Project Number",
    "Design Count",
    "Designs",
    "Coordinate Summary",
    "Device Count",
    "Machine Count",
)

DEVICE_KEYS: tuple[str, ...] = (
    "Name",
    "Trimble Device ID",
    "Project",
    "Trimble Project ID",
    "Application",
    "App Version",
    "OS",
    "OS Version",
    "Locale",
    "Associated Machine ID",
    "Latitude",
    "Longitude",
    "Ellipsoidal Height",
    "Correction Source",
    "Last Reported",
    "Assigned Designs",
)

MACHINE_KEYS: tuple[str, ...] = (
    "Name",
    "Trimble Machine ID",
    "Project",
    "Trimble Project ID",
    "Type",
    "Serial Number",
    "Make",
    "Model",
    "Operator",
    "Associated Device ID",
)


@dataclass
class EntityStats:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: int = 0


@dataclass
class SyncSummary:
    trimble_projects: int = 0
    trimble_devices: int = 0
    trimble_machines: int = 0
    trimble_devices_assigned: int = 0
    projects: EntityStats = field(default_factory=EntityStats)
    devices: EntityStats = field(default_factory=EntityStats)
    machines: EntityStats = field(default_factory=EntityStats)
    warnings: list[str] = field(default_factory=list)


def _project_props(record: ProjectRecord, synced_at: str) -> dict[str, Any]:
    coord = record.coordinate_summary
    if not coord and record.coordinate_entries:
        from mapping import coordinate_summary

        coord = coordinate_summary(record.coordinate_entries)
    return {
        "Name": title(record.name),
        "Trimble Project ID": rich_text(record.project_id),
        "Project Number": rich_text(extract_project_number(record.name)),
        "Design Count": number(len(record.designs)),
        "Designs": rich_text(design_summary(record.designs)),
        "Coordinate Summary": rich_text(coord),
        "Device Count": number(record.device_count),
        "Machine Count": number(record.machine_count),
        "Last API Sync": date_prop(synced_at),
    }


def _device_props(record: DeviceRecord, synced_at: str) -> dict[str, Any]:
    from mapping import normalize_iso_timestamp

    return {
        "Name": title(record.name),
        "Trimble Device ID": rich_text(record.device_id),
        "Project": rich_text(record.project_name),
        "Trimble Project ID": rich_text(record.project_id),
        "Application": rich_text(record.app_name),
        "App Version": rich_text(record.app_version),
        "OS": rich_text(record.os_name),
        "OS Version": rich_text(record.os_version),
        "Locale": rich_text(record.locale),
        "Associated Machine ID": rich_text(record.associated_machine_id),
        "Latitude": number(record.latitude),
        "Longitude": number(record.longitude),
        "Ellipsoidal Height": number(record.ellipsoidal_height),
        "Correction Source": rich_text(record.correction_source),
        "Last Reported": date_prop(normalize_iso_timestamp(record.last_reported)),
        "Assigned Designs": rich_text(record.assigned_designs),
        "Last API Sync": date_prop(synced_at),
    }


def _machine_props(record: MachineRecord, synced_at: str) -> dict[str, Any]:
    return {
        "Name": title(record.name),
        "Trimble Machine ID": rich_text(record.machine_id),
        "Project": rich_text(record.project_name),
        "Trimble Project ID": rich_text(record.project_id),
        "Type": rich_text(record.machine_type),
        "Serial Number": rich_text(record.serial_number),
        "Make": rich_text(record.make),
        "Model": rich_text(record.model),
        "Operator": rich_text(record.operator),
        "Associated Device ID": rich_text(record.associated_device_id),
        "Last API Sync": date_prop(synced_at),
    }


def _upsert_entity(
    notion: NotionClient,
    *,
    data_source_id: str,
    stable_property: str,
    stable_id: str,
    properties: dict[str, Any],
    compare_keys: tuple[str, ...],
    index: dict[str, Any],
    dry_run: bool,
    stats: EntityStats,
    label: str,
) -> None:
    existing = index.get(stable_id)
    if existing:
        if properties_equal(existing.properties, properties, keys=compare_keys):
            stats.unchanged += 1
            log("UNCHANGED", label)
            return
        if dry_run:
            stats.updated += 1
            log("UPDATE", f"{label} (dry-run)")
            return
        notion.update_page(existing.page_id, properties)
        stats.updated += 1
        log("UPDATE", label)
        return

    if dry_run:
        stats.created += 1
        log("CREATE", f"{label} (dry-run)")
        return
    notion.create_page(data_source_id, properties)
    stats.created += 1
    log("CREATE", label)


class SyncEngine:
    def __init__(
        self,
        notion: NotionClient,
        *,
        projects_ds: str,
        devices_ds: str,
        machines_ds: str,
        dry_run: bool,
    ) -> None:
        self._notion = notion
        self._projects_ds = projects_ds
        self._devices_ds = devices_ds
        self._machines_ds = machines_ds
        self._dry_run = dry_run

    def run(self, snapshot: TrimbleSnapshot) -> SyncSummary:
        summary = SyncSummary(
            trimble_projects=len(snapshot.projects),
            trimble_devices=len(snapshot.devices),
            trimble_machines=len(snapshot.machines),
            trimble_devices_assigned=snapshot.devices_with_project_assignment,
        )

        log("NOTION", "Loading existing Projects index")
        project_index = self._notion.index_by_rich_text(
            self._projects_ds, "Trimble Project ID"
        )
        log("NOTION", "Loading existing Devices index")
        device_index = self._notion.index_by_rich_text(
            self._devices_ds, "Trimble Device ID"
        )
        log("NOTION", "Loading existing Machines index")
        machine_index = self._notion.index_by_rich_text(
            self._machines_ds, "Trimble Machine ID"
        )

        synced_at = iso_now()

        for project in snapshot.projects:
            props = _project_props(project, synced_at)
            label = f"Project {project.name} ({project.project_id})"

            def _project_job(
                p=project,
                pr=props,
                lb=label,
            ) -> None:
                _upsert_entity(
                    self._notion,
                    data_source_id=self._projects_ds,
                    stable_property="Trimble Project ID",
                    stable_id=p.project_id,
                    properties=pr,
                    compare_keys=PROJECT_KEYS,
                    index=project_index,
                    dry_run=self._dry_run,
                    stats=summary.projects,
                    label=lb,
                )

            if not run_with_notion_errors(label, _project_job, summary.warnings):
                summary.projects.errors += 1

        for device in snapshot.devices:
            props = _device_props(device, synced_at)
            label = f"Device {device.name} ({device.device_id})"

            def _device_job(d=device, pr=props, lb=label) -> None:
                _upsert_entity(
                    self._notion,
                    data_source_id=self._devices_ds,
                    stable_property="Trimble Device ID",
                    stable_id=d.device_id,
                    properties=pr,
                    compare_keys=DEVICE_KEYS,
                    index=device_index,
                    dry_run=self._dry_run,
                    stats=summary.devices,
                    label=lb,
                )

            if not run_with_notion_errors(label, _device_job, summary.warnings):
                summary.devices.errors += 1

        for machine in snapshot.machines:
            props = _machine_props(machine, synced_at)
            label = f"Machine {machine.name} ({machine.machine_id})"

            def _machine_job(m=machine, pr=props, lb=label) -> None:
                _upsert_entity(
                    self._notion,
                    data_source_id=self._machines_ds,
                    stable_property="Trimble Machine ID",
                    stable_id=m.machine_id,
                    properties=pr,
                    compare_keys=MACHINE_KEYS,
                    index=machine_index,
                    dry_run=self._dry_run,
                    stats=summary.machines,
                    label=lb,
                )

            if not run_with_notion_errors(label, _machine_job, summary.warnings):
                summary.machines.errors += 1

        return summary
