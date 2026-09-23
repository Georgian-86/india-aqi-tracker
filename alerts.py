"""Open, update and close GitHub issues for severe air-quality episodes.

Based on the latest full-day mean in data/aqi_daily.csv, per city:

- mean >= ALERT_AQI (Hazardous) for MIN_STREAK days, none open -> open an issue
- an alert is open and the day hasn't been reported          -> comment once
- mean <  CLEAR_AQI (below Very Unhealthy) and alert is open  -> comment, close

Thresholds were chosen by replaying 572 days of real data (Feb 2025 -
Sep 2026). The first version (open at 201, close at 151, from one monsoon)
would have kept Delhi's issue open 53% of the time and Kolkata's for 108
days straight. With 301 / 3 days / 201 it's ~7 issues a year, open ~11% of
the time, median episode 3 days: alerts for exceptional episodes, not for
Delhi's normal.

Opening and closing at different thresholds (hysteresis) stops an issue
flapping open/closed when a city hovers around one line. Every post carries
a hidden date marker that is also appended to the issue body, so the body
records every day reported on. Re-runs and the backup cron never double-post,
and a day never reopens an alert, even one closed by hand.

Needs GITHUB_TOKEN and GITHUB_REPOSITORY (both set in Actions); without
them it prints what it would do and exits 0, so it's safe to run locally.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

from common import CITIES, DAILY_CSV_PATH, aqi_category, read_rows

ALERT_AQI = 301  # start of "Hazardous"
MIN_STREAK = 3  # consecutive days at or above ALERT_AQI before opening
CLEAR_AQI = 201  # start of "Very Unhealthy"; close only once below it
LABEL = "aqi-alert"
API = "https://api.github.com"
TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class CityDay:
    city: str
    date: str
    mean: float
    peak: str
    streak: int  # consecutive days ending at `date` with mean >= ALERT_AQI


@dataclass(frozen=True)
class Action:
    kind: str  # "open" | "comment" | "close"
    city: str
    body: str
    title: str = ""
    issue: int | None = None
    new_issue_body: str = ""  # for comment/close: body with the day's marker appended


def city_marker(city: str) -> str:
    return f"<!-- aqi-alert-city:{city} -->"


def date_marker(day: str) -> str:
    return f"<!-- aqi-alert-date:{day} -->"


DATE_MARKER_RE = re.compile(r"<!-- aqi-alert-date:(\d{4}-\d{2}-\d{2}) -->")


def dates_in(texts: list[str]) -> set[str]:
    return {d for t in texts for d in DATE_MARKER_RE.findall(t)}


def latest_days(daily_rows: list[dict[str, str]]) -> list[CityDay]:
    """Latest full day per city, with the length of its current severe streak."""
    result = []
    for city, _, _ in CITIES:
        rows = sorted(
            (r for r in daily_rows if r["city"] == city and r["us_aqi_mean"]),
            key=lambda r: r["date"],
        )
        if not rows:
            continue
        streak = 0
        for r in reversed(rows):
            if float(r["us_aqi_mean"]) < ALERT_AQI:
                break
            streak += 1
        last = rows[-1]
        result.append(CityDay(city, last["date"], float(last["us_aqi_mean"]),
                              last["us_aqi_max"], streak))
    return result


def _describe(day: CityDay) -> str:
    return (
        f"**{day.city}**, {day.date}: full-day mean US AQI **{day.mean:.0f}** "
        f"({aqi_category(day.mean)}), peak hour {day.peak}."
    )


def plan(
    days: list[CityDay],
    open_issues: dict[str, tuple[int, str]],
    closed_dates: dict[str, set[str]] | None = None,
) -> list[Action]:
    """Decide what to post. Pure: no I/O, so it's easy to test.

    open_issues maps city -> (open alert issue number, its body); the dates
    already reported are read from the body's markers. closed_dates maps
    city -> dates recorded on its closed alert issues.
    """
    closed_dates = closed_dates or {}
    actions = []
    footer = (
        "\n\n<sub>Automated by the daily AQI workflow · data: CAMS via Open-Meteo "
        "(CC BY 4.0) · model estimates, not station readings.</sub>"
    )
    for day in days:
        number, issue_body = open_issues.get(day.city, (None, ""))
        markers = city_marker(day.city) + date_marker(day.date)
        if number is None:
            if (
                day.mean >= ALERT_AQI
                and day.streak >= MIN_STREAK
                and day.date not in closed_dates.get(day.city, set())
            ):
                days_txt = f" for {day.streak} days running"
                actions.append(Action(
                    "open", day.city,
                    title=f"AQI alert: {day.city} is {aqi_category(day.mean)} ({day.date})",
                    body=(
                        f"{_describe(day)}\n\nAir quality has been at or above "
                        f"{aqi_category(ALERT_AQI)} ({ALERT_AQI}){days_txt}. This issue gets a "
                        f"comment each day and closes automatically once the daily "
                        f"mean drops below {CLEAR_AQI}.{footer}{markers}"
                    ),
                ))
            continue
        if day.date in dates_in([issue_body]):
            continue  # already posted about this day
        new_issue_body = issue_body + date_marker(day.date)
        if day.mean < CLEAR_AQI:
            actions.append(Action(
                "close", day.city, issue=number, new_issue_body=new_issue_body,
                body=f"{_describe(day)}\n\nBack below {aqi_category(CLEAR_AQI)} ({CLEAR_AQI}); "
                     f"closing.{footer}{markers}",
            ))
        else:
            actions.append(Action(
                "comment", day.city, issue=number, new_issue_body=new_issue_body,
                body=f"{_describe(day)}{footer}{markers}",
            ))
    return actions


class GitHub:
    def __init__(self, repo: str, token: str, session: requests.Session | None = None):
        self.repo = repo
        self.session = session or requests.Session()
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _call(self, method: str, path: str, **kwargs):
        resp = self.session.request(
            method, f"{API}/repos/{self.repo}{path}",
            headers=self.headers, timeout=TIMEOUT_SECONDS, **kwargs,
        )
        if resp.status_code >= 300:
            raise requests.HTTPError(f"{method} {path}: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json()

    def alert_issues(self) -> tuple[dict[str, tuple[int, str]], dict[str, set[str]]]:
        """Open alerts as city -> (number, body), and city -> dates on closed ones.

        Only the 100 most recently updated alert issues are considered, which
        covers well over a year of episodes.
        """
        issues = self._call("GET", "/issues", params={
            "labels": LABEL, "state": "all", "sort": "updated", "per_page": 100,
        })
        open_alerts: dict[str, tuple[int, str]] = {}
        closed: dict[str, set[str]] = {}
        for issue in issues:
            body = issue.get("body") or ""
            for city, _, _ in CITIES:
                if city_marker(city) not in body:
                    continue
                if issue.get("state") == "open":
                    open_alerts[city] = (issue["number"], body)
                else:
                    closed.setdefault(city, set()).update(dates_in([body]))
        return open_alerts, closed

    def apply(self, action: Action) -> None:
        if action.kind == "open":
            self._call("POST", "/issues", json={
                "title": action.title, "body": action.body, "labels": [LABEL],
            })
            return
        # Record the day on the issue body first: if the comment then fails,
        # the day is skipped rather than posted twice on the retry.
        update = {"body": action.new_issue_body}
        if action.kind == "close":
            update |= {"state": "closed", "state_reason": "completed"}
        self._call("PATCH", f"/issues/{action.issue}", json=update)
        self._call("POST", f"/issues/{action.issue}/comments", json={"body": action.body})


def main(
    daily_csv_path: Path = DAILY_CSV_PATH,
    env: dict[str, str] | None = None,
    session: requests.Session | None = None,
) -> int:
    env = os.environ if env is None else env
    days = latest_days(read_rows(daily_csv_path))
    token, repo = env.get("GITHUB_TOKEN"), env.get("GITHUB_REPOSITORY")

    if not token or not repo:
        print("GITHUB_TOKEN/GITHUB_REPOSITORY not set: dry run, showing new alerts only.")
        for a in plan(days, {}):
            print(f"would {a.kind}: {a.title}")
        return 0

    gh = GitHub(repo, token, session)
    try:
        open_issues, closed_dates = gh.alert_issues()
        actions = plan(days, open_issues, closed_dates)
        for a in actions:
            gh.apply(a)
            print(f"{a.kind}: {a.city} {a.title or f'#{a.issue}'}")
    except (requests.RequestException, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not actions:
        print("No alert changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
