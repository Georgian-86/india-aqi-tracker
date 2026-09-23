import copy
import json
from pathlib import Path

import pytest
import requests

FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_response.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def make_response(status=200, body=None):
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(body if body is not None else {}).encode()
    return resp


class FakeSession:
    """Stands in for requests.Session: replays a scripted list of outcomes."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return copy.deepcopy(outcome)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if anything tries to use the real network."""

    def blocked(*args, **kwargs):
        raise RuntimeError("Network access attempted in tests")

    monkeypatch.setattr(requests.Session, "get", blocked)
    monkeypatch.setattr(requests, "get", blocked)
