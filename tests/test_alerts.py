import json

import pytest
import requests

import alerts
import fetch
from alerts import ALERT_AQI, CLEAR_AQI, CityDay


class FakeGitHub:
    """In-memory stand-in for the GitHub REST endpoints alerts.py uses."""

    def __init__(self, fail_on=None):
        self.issues = {}  # number -> {"number", "title", "body", "state", "labels"}
        self.comments = {}  # number -> [body]
        self.calls = []
        self.fail_on = fail_on

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        path = url.split("/repos/owner/repo", 1)[1]
        self.calls.append((method, path))
        assert headers["Authorization"] == "Bearer t0ken"
        if self.fail_on == (method, path):
            return self._resp(500, {"message": "boom"})
        if method == "GET" and path == "/issues":
            assert params["labels"] == alerts.LABEL and params["state"] == "all"
            return self._resp(200, list(self.issues.values()))
        if method == "POST" and path == "/issues":
            n = len(self.issues) + 1
            self.issues[n] = {"number": n, "state": "open", **json}
            self.comments[n] = []
            return self._resp(201, self.issues[n])
        number = int(path.split("/")[2])
        if method == "PATCH":
            self.issues[number].update(json)
            return self._resp(200, self.issues[number])
        if method == "POST" and path.endswith("/comments"):
            self.comments[number].append(json["body"])
            return self._resp(201, {})
        raise AssertionError(f"unexpected call {method} {path}")

    @staticmethod
    def _resp(status, body):
        r = requests.Response()
        r.status_code = status
        r._content = json.dumps(body).encode()
        return r


ENV = {"GITHUB_TOKEN": "t0ken", "GITHUB_REPOSITORY": "owner/repo"}


def row(day, city, mean, peak="250"):
    return {"date": day, "city": city, "hours": "24", "us_aqi_mean": str(mean),
            "us_aqi_max": peak, "pm2_5_mean": "", "pm10_mean": "", "fetched_at_utc": "x"}


def write_daily(path, rows):
    fetch.append_rows(path, rows, fetch.DAILY_COLUMNS)


def run(tmp_path, gh, rows, name="d.csv"):
    path = tmp_path / name
    path.unlink(missing_ok=True)
    write_daily(path, rows)
    return alerts.main(path, env=ENV, session=gh)


# --- pure logic ------------------------------------------------------------

def test_latest_days_streak_and_order():
    rows = [row("2026-09-20", "Delhi", 250), row("2026-09-22", "Delhi", 230),
            row("2026-09-21", "Delhi", 210), row("2026-09-19", "Delhi", 150),
            row("2026-09-22", "Mumbai", 60)]
    days = {d.city: d for d in alerts.latest_days(rows)}
    assert days["Delhi"] == CityDay("Delhi", "2026-09-22", 230.0, "250", 3)
    assert days["Mumbai"].streak == 0
    assert "Chennai" not in days


@pytest.mark.parametrize("mean, opens", [(ALERT_AQI - 1, False), (ALERT_AQI, True), (620, True)])
def test_plan_opens_only_at_alert_threshold(mean, opens):
    actions = alerts.plan([CityDay("Delhi", "2026-09-22", mean, "700", 1)], {})
    assert [a.kind for a in actions] == (["open"] if opens else [])


def test_plan_open_issue_body_carries_markers():
    [a] = alerts.plan([CityDay("Delhi", "2026-09-22", 320, "410", 2)], {})
    assert a.title == "AQI alert: Delhi is Hazardous (2026-09-22)"
    assert "for 2 days running" in a.body
    assert alerts.city_marker("Delhi") in a.body
    assert alerts.dates_in([a.body]) == {"2026-09-22"}
    assert "CAMS via Open-Meteo" in a.body


def test_plan_hysteresis_keeps_issue_open_between_thresholds():
    body = alerts.city_marker("Delhi") + alerts.date_marker("2026-09-21")
    [a] = alerts.plan([CityDay("Delhi", "2026-09-22", 170, "190", 0)], {"Delhi": (7, body)})
    assert a.kind == "comment" and a.issue == 7  # 151 <= 170 < 201: stays open
    assert alerts.dates_in([a.new_issue_body]) == {"2026-09-21", "2026-09-22"}


def test_plan_closes_below_clear_threshold():
    body = alerts.city_marker("Delhi") + alerts.date_marker("2026-09-21")
    [a] = alerts.plan([CityDay("Delhi", "2026-09-22", CLEAR_AQI - 1, "160", 0)],
                      {"Delhi": (7, body)})
    assert a.kind == "close"


def test_plan_skips_day_already_reported():
    body = alerts.city_marker("Delhi") + alerts.date_marker("2026-09-22")
    assert alerts.plan([CityDay("Delhi", "2026-09-22", 300, "310", 1)], {"Delhi": (7, body)}) == []


def test_plan_never_reopens_for_a_day_on_a_closed_issue():
    day = CityDay("Delhi", "2026-09-22", 300, "310", 3)
    assert alerts.plan([day], {}, {"Delhi": {"2026-09-22"}}) == []
    # ...but the next bad day opens a fresh alert.
    nxt = CityDay("Delhi", "2026-09-23", 300, "310", 4)
    assert [a.kind for a in alerts.plan([nxt], {}, {"Delhi": {"2026-09-22"}})] == ["open"]


# --- end to end against the fake API ---------------------------------------

def test_episode_lifecycle(tmp_path):
    gh = FakeGitHub()
    history = [row("2026-09-20", "Delhi", 120), row("2026-09-20", "Mumbai", 60)]

    # Day 1: Delhi turns Very Unhealthy -> issue opened, Mumbai untouched.
    history += [row("2026-09-21", "Delhi", 240), row("2026-09-21", "Mumbai", 70)]
    assert run(tmp_path, gh, history) == 0
    assert len(gh.issues) == 1 and gh.issues[1]["state"] == "open"
    assert gh.issues[1]["labels"] == [alerts.LABEL]

    # Backup run the same day: nothing new.
    calls = len(gh.calls)
    assert run(tmp_path, gh, history) == 0
    assert gh.calls[calls:] == [("GET", "/issues")]

    # Day 2: Unhealthy (between thresholds) -> one comment, still open.
    history.append(row("2026-09-22", "Delhi", 180))
    assert run(tmp_path, gh, history) == 0
    assert gh.issues[1]["state"] == "open" and len(gh.comments[1]) == 1

    # Day 3: back to Moderate -> closing comment and closed.
    history.append(row("2026-09-23", "Delhi", 90))
    assert run(tmp_path, gh, history) == 0
    assert gh.issues[1]["state"] == "closed"
    assert gh.issues[1]["state_reason"] == "completed"
    assert "closing" in gh.comments[1][-1]
    assert alerts.dates_in([gh.issues[1]["body"]]) == {"2026-09-21", "2026-09-22", "2026-09-23"}

    # Re-run after closing: no reopen, no new issue.
    assert run(tmp_path, gh, history) == 0
    assert len(gh.issues) == 1


def test_manual_close_mid_episode_does_not_reopen_same_day(tmp_path):
    gh = FakeGitHub()
    history = [row("2026-09-21", "Delhi", 240), row("2026-09-22", "Delhi", 260)]
    run(tmp_path, gh, history[:1])
    run(tmp_path, gh, history)  # day 2 recorded on the issue
    gh.issues[1]["state"] = "closed"  # someone closes it by hand
    assert run(tmp_path, gh, history) == 0
    assert len(gh.issues) == 1  # not reopened for 2026-09-22
    history.append(row("2026-09-23", "Delhi", 280))
    run(tmp_path, gh, history)
    assert len(gh.issues) == 2  # a new bad day does open a fresh alert


def test_one_issue_per_city(tmp_path):
    gh = FakeGitHub()
    rows = [row("2026-09-22", "Delhi", 300), row("2026-09-22", "Kolkata", 210)]
    assert run(tmp_path, gh, rows) == 0
    assert sorted(i["title"].split()[2] for i in gh.issues.values()) == ["Delhi", "Kolkata"]


def test_api_error_exits_nonzero(tmp_path, capsys):
    gh = FakeGitHub(fail_on=("POST", "/issues"))
    assert run(tmp_path, gh, [row("2026-09-22", "Delhi", 300)]) == 1
    assert "HTTP 500" in capsys.readouterr().err


def test_dry_run_without_token(tmp_path, capsys):
    path = tmp_path / "d.csv"
    write_daily(path, [row("2026-09-22", "Delhi", 300)])
    assert alerts.main(path, env={}) == 0
    assert "would open: AQI alert: Delhi" in capsys.readouterr().out
