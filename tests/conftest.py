import copy
import hashlib
import json
from pathlib import Path

import pytest
import requests

FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_response.json"
REPO = Path(__file__).resolve().parent.parent
# Real outputs. The daily workflow runs pytest right before committing these,
# so a test that writes here would publish fixture data as real data.
PROTECTED = [REPO / "data", REPO / "charts", REPO / "reports", REPO / "README.md"]


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
    monkeypatch.setattr(requests.Session, "request", blocked)
    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(requests, "request", blocked)


def _snapshot() -> dict[str, str]:
    files = []
    for p in PROTECTED:
        files += [f for f in p.rglob("*") if f.is_file()] if p.is_dir() else [p]
    return {
        str(f.relative_to(REPO)): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in files
        if f.exists()
    }


@pytest.fixture(autouse=True)
def protect_real_outputs():
    """Fail any test that creates, modifies or deletes the repo's real outputs."""
    before = _snapshot()
    yield
    after = _snapshot()
    assert after == before, (
        "Test modified real repo outputs; use tmp_path instead. Changed: "
        f"{sorted(set(before.items()) ^ set(after.items()))}"
    )
