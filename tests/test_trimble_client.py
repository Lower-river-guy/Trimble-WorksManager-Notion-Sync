from trimble_client import TrimbleClient


class DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def test_pagination_follows_next(monkeypatch):
    client = TrimbleClient(
        client_id="id",
        client_secret="secret",
        base_url="https://example.test/v1/",
        token_url="https://example.test/token",
        scope="site-management",
        account_trn="acct",
    )

    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        if "page=1" in url:
            return DummyResponse(
                {
                    "items": [{"id": "a"}],
                    "links": {"next": {"href": "https://example.test/v1/items?page=2"}},
                }
            )
        return DummyResponse({"items": [{"id": "b"}], "links": {}})

    client._session.get = fake_get  # type: ignore[method-assign]
    items = client.paginate("https://example.test/v1/items?page=1")
    assert [x["id"] for x in items] == ["a", "b"]
    assert len(calls) == 2


def test_trimble_api_failure_handling(monkeypatch):
    client = TrimbleClient(
        client_id="id",
        client_secret="secret",
        base_url="https://example.test/v1/",
        token_url="https://example.test/token",
        scope="site-management",
        account_trn="acct",
    )

    def fail_get(url, timeout):
        return DummyResponse({"message": "fail"}, status_code=500)

    client._session.get = fail_get  # type: ignore[method-assign]

    try:
        client.paginate("https://example.test/v1/items")
        assert False, "expected failure"
    except RuntimeError as exc:
        assert "HTTP 500" in str(exc)
