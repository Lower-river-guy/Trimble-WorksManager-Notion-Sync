"""Notion API client (existing databases only — no schema creation)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import requests

from log_utils import log


@dataclass(frozen=True)
class NotionPageIndex:
    page_id: str
    properties: dict[str, Any]


class NotionClient:
    BASE_URL = "https://api.notion.com/v1"

    def __init__(
        self,
        token: str,
        *,
        api_version: str = "2025-09-03",
        timeout: int = 45,
    ) -> None:
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": api_version,
                "Content-Type": "application/json",
            }
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        last_error = ""
        for attempt in range(1, 6):
            response = self._session.request(
                method,
                url,
                json=json_body,
                params=params,
                timeout=self._timeout,
            )
            if response.status_code in {429} or 500 <= response.status_code <= 599:
                if attempt < 5:
                    wait = min(2**attempt, 12)
                    log("NOTION", f"HTTP {response.status_code}; retry in {wait}s")
                    time.sleep(wait)
                    continue
            try:
                data = response.json()
            except Exception:
                data = {"message": response.text}
            if not response.ok:
                raise RuntimeError(
                    f"Notion {method} {path} failed HTTP {response.status_code}: "
                    f"code={data.get('code')} message={data.get('message')}"
                )
            if not isinstance(data, dict):
                raise RuntimeError("Notion returned unexpected payload")
            return data
        raise RuntimeError(f"Notion request failed after retries: {last_error}")

    def query_all(self, data_source_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            body: dict[str, Any] = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            data = self.request(
                "POST",
                f"/data_sources/{data_source_id}/query",
                json_body=body,
            )
            rows.extend(data.get("results") or [])
            if not data.get("has_more"):
                return rows
            cursor = data.get("next_cursor")
            if not cursor:
                return rows

    def index_by_rich_text(
        self,
        data_source_id: str,
        property_name: str,
    ) -> dict[str, NotionPageIndex]:
        index: dict[str, NotionPageIndex] = {}
        duplicates: set[str] = set()
        for page in self.query_all(data_source_id):
            page_id = page.get("id")
            props = page.get("properties") or {}
            if not isinstance(page_id, str) or not isinstance(props, dict):
                continue
            from notion_props import read_rich_text

            stable_id = read_rich_text(props.get(property_name))
            if not stable_id:
                continue
            if stable_id in index:
                duplicates.add(stable_id)
            index[stable_id] = NotionPageIndex(page_id=page_id, properties=props)
        if duplicates:
            raise RuntimeError(
                f"Duplicate Notion rows for {property_name}: "
                + ", ".join(sorted(duplicates)[:10])
            )
        return index

    def create_page(self, data_source_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self.request(
            "POST",
            "/pages",
            json_body={
                "parent": {"type": "data_source_id", "data_source_id": data_source_id},
                "properties": properties,
            },
        )

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/pages/{page_id}",
            json_body={"properties": properties},
        )

    def verify_data_source(self, data_source_id: str) -> str:
        ds = self.request("GET", f"/data_sources/{data_source_id}")
        return str(ds.get("name") or ds.get("title") or data_source_id)


def run_with_notion_errors(
    label: str,
    fn: Callable[[], None],
    errors: list[str],
) -> bool:
    try:
        fn()
        return True
    except Exception as exc:
        errors.append(f"{label}: {exc}")
        log("ERROR", f"{label}: {exc}")
        return False
