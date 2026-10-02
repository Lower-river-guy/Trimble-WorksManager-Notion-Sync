"""Trimble Site Management API client (GET only)."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import requests

from log_utils import log
from mapping import assigned_design_summary, coordinate_summary, coordinate_system_summary


@dataclass
class ProjectRecord:
    project_id: str
    name: str
    designs: list[dict[str, Any]] = field(default_factory=list)
    coordinate_summary: str = ""
    device_count: int = 0
    machine_count: int = 0
    coordinate_entries: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DeviceRecord:
    device_id: str
    name: str
    project_name: str = ""
    project_id: str = ""
    app_name: str = ""
    app_version: str = ""
    os_name: str = ""
    os_version: str = ""
    locale: str = ""
    associated_machine_id: str = ""
    latitude: float | None = None
    longitude: float | None = None
    ellipsoidal_height: float | None = None
    correction_source: str = ""
    last_reported: str | None = None
    assigned_designs: str = ""


@dataclass
class MachineRecord:
    machine_id: str
    name: str
    project_name: str = ""
    project_id: str = ""
    machine_type: str = ""
    serial_number: str = ""
    make: str = ""
    model: str = ""
    operator: str = ""
    associated_device_id: str = ""


@dataclass
class TrimbleSnapshot:
    account_id: str
    projects: list[ProjectRecord]
    devices: list[DeviceRecord]
    machines: list[MachineRecord]
    devices_with_project_assignment: int = 0


class TrimbleClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        base_url: str,
        token_url: str,
        scope: str,
        account_trn: str,
        timeout: int = 45,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = base_url if base_url.endswith("/") else f"{base_url}/"
        self._token_url = token_url
        self._scope = scope
        self._account_trn = account_trn.strip()
        self._timeout = timeout
        self._session = requests.Session()

    def authenticate(self) -> None:
        basic = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode("utf-8")
        ).decode("ascii")
        response = requests.post(
            self._token_url,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={"grant_type": "client_credentials", "scope": self._scope},
            timeout=self._timeout,
        )
        if not response.ok:
            raise RuntimeError(
                f"Trimble token request failed HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
        token = response.json().get("access_token")
        if not token:
            raise RuntimeError("Trimble token response missing access_token")
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )
        log("AUTH", "Trimble client-credentials token acquired")

    def _get(self, url: str) -> dict[str, Any]:
        response = self._session.get(url, timeout=self._timeout)
        if response.status_code >= 400:
            raise RuntimeError(
                f"GET {url} failed HTTP {response.status_code}: {response.text[:300]}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected non-object JSON from {url}")
        return payload

    def _get_soft(self, url: str) -> dict[str, Any] | None:
        try:
            return self._get(url)
        except Exception as exc:
            log("WARNING", f"Optional GET failed {url}: {exc}")
            return None

    @staticmethod
    def _link(payload: dict[str, Any], rel: str) -> str:
        links = payload.get("links") or payload.get("_links") or {}
        if isinstance(links, dict):
            entry = links.get(rel)
            if isinstance(entry, str):
                return entry
            if isinstance(entry, dict):
                return str(entry.get("href") or entry.get("url") or "")
        if isinstance(links, list):
            for item in links:
                if not isinstance(item, dict):
                    continue
                if str(item.get("rel") or "").casefold() == rel.casefold():
                    return str(item.get("href") or "")
        return ""

    def paginate(self, first_url: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        url = first_url
        visited: set[str] = set()
        while url and url not in visited:
            visited.add(url)
            page = self._get(url)
            page_items = page.get("items") or []
            if isinstance(page_items, list):
                items.extend(x for x in page_items if isinstance(x, dict))
            url = self._link(page, "next")
        return items

    def resolve_account_id(self) -> str:
        root = self._get(self._base_url)
        accounts_url = self._link(root, "accounts") or f"{self._base_url}accounts"
        accounts_page = self._get(accounts_url)
        account_items = accounts_page.get("items") or []
        if not isinstance(account_items, list) or not account_items:
            raise RuntimeError("Trimble returned no accounts")

        if self._account_trn:
            for account in account_items:
                if not isinstance(account, dict):
                    continue
                if str(account.get("id") or "") == self._account_trn:
                    log("ACCOUNT", self._account_trn)
                    return self._account_trn

        account_id = str(account_items[0].get("id") or "")
        if not account_id:
            raise RuntimeError("Trimble account id missing")
        log("ACCOUNT", account_id)
        return account_id

    def fetch_snapshot(self) -> TrimbleSnapshot:
        account_id = self.resolve_account_id()

        projects_url = self._link(self._get(self._base_url), "projects")
        if not projects_url:
            projects_url = f"{self._base_url}projects?accountId={account_id}"

        raw_projects = self.paginate(projects_url)
        log("PROJECTS", f"Trimble returned {len(raw_projects)} projects")

        device_projects: dict[str, list[tuple[str, str]]] = {}
        machine_projects: dict[str, list[tuple[str, str]]] = {}
        project_records: list[ProjectRecord] = []
        project_device_coords: dict[str, list[dict[str, Any]]] = {}

        for project in raw_projects:
            pid = str(project.get("id") or "").strip()
            pname = str(project.get("name") or "").strip() or "(unnamed)"
            if not pid:
                continue

            designs_url = self._link(project, "designs")
            designs = self.paginate(designs_url) if designs_url else []

            coord_detail = None
            for rel in ("coordinateSystem", "coordinateSystems", "coordinate-system"):
                coord_url = self._link(project, rel)
                if coord_url:
                    coord_detail = self._get_soft(coord_url)
                    if coord_detail:
                        break

            devices_url = self._link(project, "devices")
            project_devices = self.paginate(devices_url) if devices_url else []
            machines_url = self._link(project, "machines")
            project_machines = self.paginate(machines_url) if machines_url else []

            coord_entries: list[dict[str, Any]] = []
            for device in project_devices:
                did = str(device.get("id") or "").strip()
                if not did:
                    continue
                device_projects.setdefault(did, []).append((pid, pname))
                coords_url = self._link(device, "coordinates")
                if coords_url:
                    coords = self._get_soft(coords_url)
                    if coords:
                        entry = dict(coords)
                        entry["deviceId"] = did
                        coord_entries.append(entry)

            for machine in project_machines:
                mid = str(machine.get("id") or "").strip()
                if mid:
                    machine_projects.setdefault(mid, []).append((pid, pname))

            project_device_coords[pid] = coord_entries
            project_records.append(
                ProjectRecord(
                    project_id=pid,
                    name=pname,
                    designs=designs,
                    coordinate_summary=coordinate_system_summary(project, coord_detail),
                    device_count=len(project_devices),
                    machine_count=len(project_machines),
                    coordinate_entries=coord_entries,
                )
            )

        devices_url = (
            f"{self._base_url}accounts/{account_id}/devices"
            "?pageIndex=0&pageSize=100"
        )
        raw_devices = self.paginate(devices_url)
        log("DEVICES", f"Trimble returned {len(raw_devices)} devices")

        device_designs: dict[str, list[dict[str, Any]]] = {}
        for device in raw_devices:
            did = str(device.get("id") or "").strip()
            if not did:
                continue
            designs_url = self._link(device, "designs")
            if designs_url:
                device_designs[did] = self.paginate(designs_url)

        devices: list[DeviceRecord] = []
        assigned_count = 0
        for device in raw_devices:
            did = str(device.get("id") or "").strip()
            if not did:
                continue
            pairs = device_projects.get(did, [])
            if pairs:
                assigned_count += 1
            from mapping import join_project_labels

            project_name, project_id = join_project_labels(pairs)

            coords_url = self._link(device, "coordinates")
            coords = self._get_soft(coords_url) if coords_url else None

            def _num(key: str) -> float | None:
                if not coords:
                    return None
                val = coords.get(key)
                try:
                    return None if val is None else float(val)
                except Exception:
                    return None

            devices.append(
                DeviceRecord(
                    device_id=did,
                    name=str(device.get("name") or did),
                    project_name=project_name,
                    project_id=project_id,
                    app_name=str(device.get("appName") or ""),
                    app_version=str(device.get("appVersion") or ""),
                    os_name=str(device.get("osName") or ""),
                    os_version=str(device.get("osVersion") or ""),
                    locale=str(device.get("locale") or ""),
                    associated_machine_id=str(device.get("associatedMachineId") or ""),
                    latitude=_num("lat"),
                    longitude=_num("lon"),
                    ellipsoidal_height=_num("ellipsoidalHeight"),
                    correction_source=str((coords or {}).get("correctionSource") or ""),
                    last_reported=(coords or {}).get("lastReportedAt"),
                    assigned_designs=assigned_design_summary(device_designs.get(did, [])),
                )
            )

        machines_url = (
            f"{self._base_url}accounts/{account_id}/machines"
            "?pageIndex=0&pageSize=100"
        )
        raw_machines = self.paginate(machines_url)
        log("MACHINES", f"Trimble returned {len(raw_machines)} machines")

        machines: list[MachineRecord] = []
        for machine in raw_machines:
            mid = str(machine.get("id") or "").strip()
            if not mid:
                continue
            from mapping import join_project_labels

            project_name, project_id = join_project_labels(machine_projects.get(mid, []))
            machines.append(
                MachineRecord(
                    machine_id=mid,
                    name=str(machine.get("name") or mid),
                    project_name=project_name,
                    project_id=project_id,
                    machine_type=str(machine.get("type") or ""),
                    serial_number=str(machine.get("serialNumber") or ""),
                    make=str(machine.get("make") or ""),
                    model=str(machine.get("model") or ""),
                    operator=str(machine.get("operator") or ""),
                    associated_device_id=str(machine.get("associatedDeviceId") or ""),
                )
            )

        for project in project_records:
            if not project.coordinate_summary and project.coordinate_entries:
                project.coordinate_summary = coordinate_summary(project.coordinate_entries)

        return TrimbleSnapshot(
            account_id=account_id,
            projects=project_records,
            devices=devices,
            machines=machines,
            devices_with_project_assignment=assigned_count,
        )
