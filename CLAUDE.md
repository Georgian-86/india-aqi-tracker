# CLAUDE.md

Git-scraping project: a daily GitHub Actions job records air quality for
Delhi, Mumbai, Bengaluru, Kolkata, Chennai, Hyderabad, Pune and Ahmedabad from the
Open-Meteo Air Quality API (CAMS data) into
`data/aqi.csv`, then redraws a chart and a README section.

## Layout

- `common.py` holds the single source of truth: `CITIES` (name, lat, lon, **order matters**),
  `COLUMNS`, file paths, `aqi_category()` (US EPA scale), `naqi()` / `naqi_subindex()`
  (India CPCB scale for PM2.5, PM10, NO₂ 24 h and O₃ 8 h, with `NAQI_BANDS` as data;
  returns a `Naqi` with the prominent pollutant and a `complete` flag for ≥ 3 pollutants),
  and `read_rows()`. India AQI is computed at render time from stored means. Don't add it as
  a CSV column. Above the last CPCB band it returns `index=None` ("Severe"); never
  extrapolate a number.
- **The data is not homogeneous over time** (CAMS model upgrades). Known steps: NO₂ in all
  cities at the end of June 2023 (about 2× before), and Delhi's March–June PM10 from 2025
  (about 4×). Don't add year-over-year or long-term trend features without handling this.
  Before adding one, compare same-month ratios across years for every city and pollutant.
  `drift.py` does that check (`check_month`: median city beyond `ALL_CITIES_RATIO`, or
  one city beyond `CITY_RATIO`, vs the same month a year earlier). Each new monthly report
  has its result as a "Data consistency" section. Its thresholds were tuned on the real
  backfill; re-run `python drift.py` on real data before changing them.
- **Don't put O₃ back into the India AQI** (`update_readme.india_result` passes no ozone).
  CAMS surface ozone is strongly biased high over India. With it, O₃ was the prominent
  pollutant almost every day in every city. Check any new pollutant against real data
  (which pollutant becomes "prominent", and how often) before trusting it.
- Gas stats (`no2_mean`, `o3_max8h`) go to `data/aqi_daily_gases.csv` (`GAS_COLUMNS`), never
  as new columns in `aqi_daily.csv`. Adding columns would mean rewriting its header, and it
  is append-only. `append_rows` uses `extrasaction="ignore"`, so one row dict can feed
  both files. Follow the same pattern for any future per-day fields.
- `fetch.py` makes one API call for all cities (`current` plus `hourly` with
  `past_days=1&forecast_days=2`). It appends the snapshot to `data/aqi.csv` and yesterday's
  full-day stats (`parse_daily`) to `data/aqi_daily.csv` (`DAILY_COLUMNS`). Both are deduped
  on `(date, city)`. `--past-days N` (1–92, workflow input `past_days`) computes stats for
  the last N complete days. That's the backfill path, and the same code the daily run uses
  with N=1. With `forecast_days=2` the same response carries tomorrow's hours:
  `parse_forecast` stores tomorrow's `day_stats` in `data/aqi_forecast.csv`
  (`FORECAST_COLUMNS`, with an `issued` day; first issue wins). A missing forecast is a
  warning, not a failure. The README and `latest.json` show a forecast only if its `issued`
  matches the latest snapshot's date, so a stale forecast is never presented as current.
  `parse_hourly` stores the same completed days' hourly values in `data/aqi_hourly.csv`
  (`HOURLY_COLUMNS`, keyed on `(date, hour, city)`, no `fetched_at_utc` to halve its size).
  `diurnal.py` turns the last 30 days into each city's cleanest/worst `WINDOW_HOURS`
  stretch (wrapping midnight; needs `MIN_DAYS` per hour); README via `render_time_of_day`.
  `forecast_skill.py` pairs forecasts with the matching `aqi_daily.csv` day (MAE, bias,
  category hit rate, last `WINDOW_DAYS`, cities with ≥ `MIN_PAIRS`). The README renders it
  via `render_forecast_skill`. Both sides are CAMS, so never describe it as accuracy against
  ground truth.
- `make_chart.py` renders `charts/aqi_trend.png` (matplotlib, `Agg` backend; `charts/` is
  git-ignored). The workflow publishes it as the only commit on the `charts` branch
  (force-pushed via `hash-object`/`mktree`/`commit-tree`). The README embeds it from
  `update_readme.CHART_URL`. Never commit chart images to main. It plots
  `us_aqi_mean` from `aqi_daily.csv`, falling back to snapshot `us_aqi` only if there's no
  daily data. It draws **small multiples**: one panel per city in a 2-column grid, with
  shared axes, daily values as a faint line and a bold 7-day mean (`rolling_mean`).
  `y_limit()` caps the shared axis at max(300, p95 × 1.15), and each panel with values above
  the cap gets one "peak N · date" note. Don't return to one multi-line chart or per-run peak
  labels: both were unreadable with a year of data. Check renders at README width (~850 px):
  keep the figure ≤ ~1150 px wide and fonts ≥ 8 pt.
- `update_readme.py` replaces the text between `<!-- AQI:START -->` and `<!-- AQI:END -->`
  with a one-line headline (`_headline`: worst/cleanest snapshot city, count Unhealthy or
  worse; omitted with < 2 cities), a snapshot table ("vs prev." is only shown when readings are within 3 h of the same
  time of day), a full-day table with a 7-day mean plus CPCB health advice (`NAQI_HEALTH`,
  Moderate or worse), and last-30-days tables on both scales (`render_summary`,
  `render_india_summary`, sharing `_summary_window`). They are omitted with fewer than 2
  days. `as_of` (today's IST date, from `main()`) adds a staleness warning when today's
  snapshot is missing. Tests pass `as_of` explicitly or leave it None.
- `alerts.py` manages GitHub issues for severe episodes, based on the latest `aqi_daily.csv`
  day. `plan()` is pure: open at ≥ `ALERT_AQI` (301) for `MIN_STREAK` (3) days, comment
  daily, close below `CLEAR_AQI` (201). These were tuned by replaying 572 days of real data
  (see the alerts.py docstring). Re-check with a replay before changing them. Tests use
  levels relative to the constants, never literal numbers. Every post appends `<!-- aqi-alert-date:YYYY-MM-DD -->` to the issue body, which
  is the source of truth for which days were reported (no double posts, no reopen for a
  reported day). Without `GITHUB_TOKEN`/`GITHUB_REPOSITORY` it does a dry run. The
  workflow needs `issues: write`.
- `backfill.py --since YYYY-MM-DD` fills `aqi_daily.csv`/`aqi_daily_gases.csv` beyond the
  92-day `past_days` limit using `start_date`/`end_date`, in 60-day chunks walking backwards.
  A chunk that gets HTTP 400 or has no data for any city ends the backfill **successfully**
  (that's how the archive's start is discovered; it isn't documented). It reuses
  `fetch.fetch_payload(params=…)`, `fetch.check_locations` and `fetch.day_stats`. The chart
  shows at most the last 365 days (`make_chart.MAX_WINDOW_DAYS`).
- **Workflow timeouts:** long-running steps get a *step* `timeout-minutes` below the job's.
  A timed-out step counts as failed, so the later `!cancelled()` steps still commit partial
  progress. A job timeout cancels everything and loses it.
- `report.py` writes `reports/YYYY-MM.md` for each completed month (last day present and at
  least `MIN_DAYS` days). **Reports are immutable**: an existing file is never rewritten. The
  index `reports/README.md` (`render_index`, one row per year) is a view, regenerated every
  run. The main README links only the latest `update_readme.RECENT_REPORTS` plus the index. It uses the same India AQI rule as the README (no O₃).
- `latest_json.py` writes `data/latest.json` (latest snapshot plus latest full day per city,
  India AQI without O₃, attribution) for other programs. It is the one file in `data/` that
  is rewritten each run. Keep it deterministic (no generation timestamp) so it only changes
  with the data. Bump `SCHEMA_VERSION` on any breaking change to its shape.
- `events.py` (workflow `events.yml`, every 3 h at :45) logs US AQI **category changes** to
  `data/aqi_events.csv` (`EVENT_COLUMNS`, keyed on `(time_ist, city)` via
  `append_rows(..., key=...)`). It commits only when a change was logged, so the number of
  commits per day follows real events. Don't add commits for any other reason. A change
  needs the reading `MARGIN` points past the edge of the recorded category (`changed()`,
  hysteresis against boundary flapping). State is the last row per city in the CSV; the
  first row per city has an empty `from_category`. It makes a small current-only request
  and validates count, order and freshness like `fetch.py`. `daily.yml` and `events.yml`
  share the `aqi-data` concurrency group so pushes never race. The README lists the
  changes from the 24 h before the snapshot (`render_events`).
- `tests/`: pytest. The fixture `tests/fixtures/open_meteo_response.json` mirrors the real
  multi-location response (a JSON array in coordinate order).
- `.github/workflows/daily.yml`: cron `17 3 * * *` (08:47 IST), a backup cron `17 6 * * *`
  (11:47 IST), and manual dispatch. Chart, README and commit steps still run when `fetch.py`
  fails, so partial data is kept. A final step then turns the job red.
- `.github/workflows/ci.yml`: `ruff check .` and `pytest` on PRs and pushes to main.
- Actions are pinned to full commit SHAs with a `# vX.Y.Z` comment, and Dependabot keeps
  both up to date. When pinning by hand, resolve with
  `git ls-remote --tags https://github.com/actions/<name>` and use the `^{}` (peeled) SHA
  if the tag is annotated.
- `.github/dependabot.yml`: monthly pip and Actions updates.

## Conventions

- **Dependencies:** runtime code uses only `requests`, `matplotlib` and the standard library.
  Target Python 3.12. Don't add pandas or other heavy deps.
- **One request:** always fetch all cities in a single call using comma-separated
  `latitude`/`longitude`. Results map to `CITIES` by index. Validate the count.
- **Dates:** `date` is the IST date taken from the API's `current.time`
  (`timezone=Asia/Kolkata`), never the runner's local clock. `fetched_at_utc` is
  `YYYY-MM-DDTHH:MM:SSZ`. Use `common.IST` for IST conversions. Never hard-code a snapshot
  time in output; derive it from `fetched_at_utc`.
- **CSV is append-only.** Never rewrite or reorder historical rows. Row order is insertion
  order (a backfill appends older dates last), so always sort by date when reading. `(date, city)` is the
  unique key. A row missing `us_aqi` is **not written**: it would permanently block that slot.
  `fetch.py` stores the other cities and exits 1 so the backup run fills the gap. Missing
  pollutant values (pm2_5, etc.) are written as empty strings. Daily stats need at least
  `MIN_DAILY_HOURS` hourly values. Otherwise that city is skipped and the run exits 1,
  though the snapshot is still stored.
- **Validate before writing:** response count, coordinates (within `COORD_TOLERANCE_DEG` of
  `CITIES`), and freshness (`current.time` no older than `MAX_DATA_AGE`). A stale response
  would otherwise dedupe to 0 rows while the run shows green.
- **Failure must be loud:** scripts return non-zero from `main()` on error so the workflow
  goes red. Retry only transient failures (network errors, timeouts, 429, 5xx) with exponential backoff.
- **Tests never write real outputs.** An autouse fixture in `conftest.py` fails any test that
  changes `data/`, `charts/` or `README.md`. The daily job runs pytest right before
  committing those. Always pass `tmp_path` paths, including `daily_csv_path`.
- **Tests never touch the network.** `tests/conftest.py` blocks `requests`. Inject a fake
  session, a no-op `sleep` and a fixed `now` into `fetch.fetch_payload` / `fetch.main`
  (see `run_main` in `tests/test_fetch.py`).
- **Dependencies are pinned exactly** in `requirements.txt`. Upgrade through Dependabot PRs.
- **Lint:** `ruff check .` must pass (CI enforces it).
- **Charts:** check them visually with 1 day and with many days of data. A short history
  gets a minimum 7-day x-window. Markers are dropped past 60 points per series.
- **Adding a city:** *append* it to the end of `CITIES` in `common.py` (never insert or
  reorder: results map to CITIES by index), add a colour in `make_chart.CITY_COLORS` (next
  unused slot of the validated palette; run the dataviz validator if you go past 8), add a
  location at the same index in the test fixture, and update the README intro and data table.
  Tests derive counts from `len(CITIES)` (`N` in `test_fetch.py`), so don't hard-code city
  counts. After merging, run the workflow once with `past_days=92` to backfill the new
  city's full-day history. Snapshots can't be backfilled.
- Generated files (`data/`, the chart, the README AQI section) are written by the workflow.
  Don't hand-edit them.
- Keep the Attribution section in README (CAMS + Open-Meteo, CC BY 4.0). It's a licence
  requirement.
- Bot commits use the message `data: AQI snapshot YYYY-MM-DD` (daily) or
  `data: AQI change YYYY-MM-DD HH:MM IST: City → Category, …` (events). Use normal descriptive
  messages for code changes.

## Commands

```bash
pip install -r requirements.txt
ruff check .
pytest
python fetch.py && python make_chart.py && python update_readme.py
```
