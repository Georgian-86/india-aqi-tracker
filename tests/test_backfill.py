import copy
import csv
from datetime import date, datetime, timedelta, timezone

import pytest
import requests

import backfill
import fetch
from common import CITIES, DAILY_COLUMNS
from conftest import FakeSession, make_response

N = len(CITIES)
NOW = datetime(2026, 9, 23, 3, 17, tzinfo=timezone.utc)


def history_payload(payload, start, end, aqi=120, blank=False):
    """The fixture's locations with an hourly block covering start..end."""
    days = (end - start).days + 1
    times = [(datetime.combine(start, datetime.min.time()) + timedelta(hours=h))
             .strftime("%Y-%m-%dT%H:%M") for h in range(days * 24)]
    out = []
    for loc in payload:
        loc = copy.deepcopy(loc)
        loc.pop("current", None)  # historical requests have no current block
        value = None if blank else aqi
        loc["hourly"] = {"time": times, "us_aqi": [value] * len(times),
                         "pm2_5": [40.0] * len(times), "pm10": [60.0] * len(times),
                         "nitrogen_dioxide": [20.0] * len(times),
                         "ozone": [50.0] * len(times)}
        out.append(loc)
    return out


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def run(tmp_path, outcomes, since, until=None):
    session = FakeSession(outcomes)
    code = backfill.main(since, until, tmp_path / "daily.csv", tmp_path / "gases.csv",
                         session=session, sleep=lambda s: None, now=NOW)
    return code, session


def test_chunks_newest_first_and_cover_range():
    ranges = backfill.chunks(date(2026, 1, 1), date(2026, 5, 10), size=60)
    assert ranges[0] == (date(2026, 3, 12), date(2026, 5, 10))
    assert ranges[-1][0] == date(2026, 1, 1)
    covered = sum((end - start).days + 1 for start, end in ranges)
    assert covered == (date(2026, 5, 10) - date(2026, 1, 1)).days + 1
    # Contiguous, no gaps or overlaps: each older chunk ends the day before the newer starts.
    for (newer_start, _), (_, older_end) in zip(ranges, ranges[1:]):
        assert older_end == newer_start - timedelta(days=1)


def test_chunk_params_use_date_range_not_current():
    params = backfill.chunk_params(date(2026, 1, 1), date(2026, 2, 28))
    assert params["start_date"] == "2026-01-01" and params["end_date"] == "2026-02-28"
    assert "current" not in params and "past_days" not in params
    assert params["hourly"] == ",".join(fetch.HOURLY_VARS)


def test_backfill_walks_back_and_stops_at_http_400(tmp_path, payload):
    since = date(2025, 12, 1)
    until = date(2026, 4, 30)
    chunks = backfill.chunks(since, until)
    assert len(chunks) == 3  # the third range is the one the API rejects
    [(s1, e1), (s2, e2), _] = chunks
    code, session = run(tmp_path, [
        make_response(200, history_payload(payload, s1, e1)),
        make_response(200, history_payload(payload, s2, e2)),
        make_response(400, {"error": True, "reason": "out of range"}),
    ], since, until)
    assert code == 0  # reaching the archive's limit isn't a failure
    assert len(session.calls) == 3
    rows = read_csv(tmp_path / "daily.csv")
    assert rows[0] == DAILY_COLUMNS
    expected_days = (e1 - s1).days + 1 + (e2 - s2).days + 1
    assert len(rows) - 1 == expected_days * N
    assert min(r[0] for r in rows[1:]) == s2.isoformat()
    assert len(read_csv(tmp_path / "gases.csv")) - 1 == expected_days * N


def test_backfill_stops_when_chunk_has_no_data(tmp_path, payload):
    since, until = date(2026, 1, 1), date(2026, 4, 30)
    [(s1, e1), (s2, e2), *_] = backfill.chunks(since, until)
    code, session = run(tmp_path, [
        make_response(200, history_payload(payload, s1, e1)),
        make_response(200, history_payload(payload, s2, e2, blank=True)),
    ], since, until)
    assert code == 0 and len(session.calls) == 2


def test_backfill_default_until_is_day_before_oldest_stored(tmp_path, payload):
    daily = tmp_path / "daily.csv"
    fetch.append_rows(daily, [{**dict.fromkeys(DAILY_COLUMNS, "1"), "date": "2026-06-23",
                               "city": "Delhi"}], DAILY_COLUMNS)
    assert backfill.default_until(daily, NOW) == date(2026, 6, 22)
    assert backfill.default_until(tmp_path / "none.csv", NOW) == date(2026, 9, 22)


def test_backfill_nothing_to_do(tmp_path, capsys):
    code, session = run(tmp_path, [], since=date(2026, 7, 1), until=date(2026, 6, 30))
    assert code == 0 and session.calls == []
    assert "Nothing to do" in capsys.readouterr().out


def test_backfill_rerun_adds_nothing(tmp_path, payload):
    since = until = date(2026, 3, 1)
    body = history_payload(payload, since, until)
    run(tmp_path, [make_response(200, body)], since, until)
    before = (tmp_path / "daily.csv").read_text()
    run(tmp_path, [make_response(200, body)], since, until)
    assert (tmp_path / "daily.csv").read_text() == before


def test_backfill_network_failure_exits_nonzero(tmp_path):
    code, _ = run(tmp_path, [requests.ConnectionError("down")] * fetch.MAX_ATTEMPTS,
                  since=date(2026, 3, 1), until=date(2026, 3, 1))
    assert code == 1


def test_backfill_rejects_misordered_response(tmp_path, payload):
    since = until = date(2026, 3, 1)
    body = history_payload(payload, since, until)
    body[0], body[1] = body[1], body[0]
    code, _ = run(tmp_path, [make_response(200, body)], since, until)
    assert code == 1
    assert not (tmp_path / "daily.csv").exists()


@pytest.mark.parametrize("argv", [[], ["--since", "not-a-date"]])
def test_cli_requires_valid_since(argv):
    with pytest.raises(SystemExit):
        backfill.cli(argv)


def timeouts(n=backfill.BACKFILL_ATTEMPTS):
    return [requests.Timeout("Read timed out.")] * n


def test_backfill_splits_a_range_that_times_out(tmp_path, payload):
    since, until = date(2026, 3, 1), date(2026, 3, 20)  # 20 days: one chunk
    newer, older = (date(2026, 3, 11), until), (since, date(2026, 3, 10))
    code, session = run(tmp_path, [
        *timeouts(),  # the 20-day range keeps timing out...
        make_response(200, history_payload(payload, *newer)),  # ...its halves don't
        make_response(200, history_payload(payload, *older)),
    ], since, until)
    assert code == 0
    ranges = [(c["params"]["start_date"], c["params"]["end_date"]) for c in session.calls]
    assert ranges[-2:] == [("2026-03-11", "2026-03-20"), ("2026-03-01", "2026-03-10")]
    assert len(read_csv(tmp_path / "daily.csv")) - 1 == 20 * N  # nothing lost
    assert all(c["timeout"] == backfill.BACKFILL_TIMEOUT_SECONDS for c in session.calls)


def test_backfill_gives_up_when_smallest_range_times_out(tmp_path, capsys):
    day = date(2026, 3, 1)
    until = day + timedelta(days=backfill.MIN_CHUNK_DAYS - 1)  # already the minimum
    code, session = run(tmp_path, timeouts(), since=day, until=until)
    assert code == 1
    assert len(session.calls) == backfill.BACKFILL_ATTEMPTS  # no further splitting
    assert "timed out" in capsys.readouterr().err


def test_backfill_keeps_earlier_ranges_when_a_later_one_fails(tmp_path, payload):
    # Mirrors the first real run: recent ranges succeed, an older one fails.
    since, until = date(2025, 12, 1), date(2026, 3, 1)  # 91 days: two chunks
    [(s1, e1), _] = backfill.chunks(since, until)
    code, _ = run(tmp_path, [
        make_response(200, history_payload(payload, s1, e1)),
        # older range: split repeatedly down to the minimum, every attempt timing out
        *timeouts(100),
    ], since, until)
    assert code == 1
    rows = read_csv(tmp_path / "daily.csv")
    assert len(rows) - 1 == ((e1 - s1).days + 1) * N  # the successful range was kept
