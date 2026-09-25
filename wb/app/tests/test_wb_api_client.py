import pytest
import requests

from app.core.wb_api import WBClient


class _DummyResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("boom", response=self)

    def json(self):
        return {"data": {"feedbacks": []}}


def test_token_normalization_strips_bearer_prefix():
    client = WBClient("  Bearer   secret-token  ")
    assert client.headers["Authorization"] == "secret-token"


def test_list_feedbacks_401_has_clear_error(monkeypatch):
    def _fake_get(*args, **kwargs):
        return _DummyResponse(status_code=401)

    monkeypatch.setattr(requests, "get", _fake_get)
    client = WBClient("token")

    with pytest.raises(RuntimeError, match="401 Unauthorized"):
        client.list_feedbacks()
