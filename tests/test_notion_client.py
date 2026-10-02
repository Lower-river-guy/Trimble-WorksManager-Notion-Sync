from notion_client import NotionClient, run_with_notion_errors


class DummyResponse:
    def __init__(self, payload, status_code=200, ok=True):
        self._payload = payload
        self.status_code = status_code
        self.ok = ok
        self.text = str(payload)

    def json(self):
        return self._payload


def test_notion_pagination(monkeypatch):
    client = NotionClient("token")

    pages = [
        {"results": [{"id": "1"}], "has_more": True, "next_cursor": "c1"},
        {"results": [{"id": "2"}], "has_more": False},
    ]

    def fake_request(method, url, json=None, params=None, timeout=None):
        payload = pages.pop(0)
        return DummyResponse(payload, status_code=200, ok=True)

    client._session.request = fake_request  # type: ignore[method-assign]
    rows = client.query_all("ds-1")
    assert [r["id"] for r in rows] == ["1", "2"]


def test_notion_api_failure_handling(monkeypatch):
    client = NotionClient("token")

    def fail_request(method, url, json=None, params=None, timeout=None):
        return DummyResponse(
            {"code": "invalid", "message": "bad"},
            status_code=400,
            ok=False,
        )

    client._session.request = fail_request  # type: ignore[method-assign]
    try:
        client.query_all("ds-1")
        assert False, "expected failure"
    except RuntimeError as exc:
        assert "HTTP 400" in str(exc)


def test_run_with_notion_errors():
    errors: list[str] = []

    def boom():
        raise RuntimeError("x")

    assert run_with_notion_errors("label", boom, errors) is False
    assert errors
