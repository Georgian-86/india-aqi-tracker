# CLAUDE.md

Git-scraping project: a daily GitHub Actions job records air quality for Delhi, Mumbai,
Bengaluru, Kolkata and Chennai from the Open-Meteo Air Quality API (CAMS data) into
`data/aqi.csv`, then redraws a chart and a README section.

## Layout

- `common.py` holds the single source of truth: `CITIES` (name, lat, lon, **order matters**),
  `COLUMNS`, file paths, `aqi_category()` (US EPA scale) and `read_rows()`.
- `fetch.py` makes one API call for all cities, parses it and appends to the CSV with dedupe.
- `make_chart.py` renders `charts/aqi_trend.png` (matplotlib, `Agg` backend).
- `update_readme.py` replaces the text between `<!-- AQI:START -->` and `<!-- AQI:END -->`.
- `tests/`: pytest. The fixture `tests/fixtures/open_meteo_response.json` mirrors the real
  multi-location response (a JSON array in coordinate order).
- `.github/workflows/daily.yml`: cron `17 3 * * *` (08:47 IST) plus manual dispatch.

## Conventions

- **Dependencies:** runtime code uses only `requests`, `matplotlib` and the standard library.
  Target Python 3.12. Don't add pandas or other heavy deps.
- **One request:** always fetch all cities in a single call using comma-separated
  `latitude`/`longitude`. Results map to `CITIES` by index. Validate the count.
- **Dates:** `date` is the IST date taken from the API's `current.time`
  (`timezone=Asia/Kolkata`), never the runner's local clock. `fetched_at_utc` is
  `YYYY-MM-DDTHH:MM:SSZ`.
- **CSV is append-only.** Never rewrite or reorder historical rows. `(date, city)` is the
  unique key. Missing API values are written as empty strings.
- **Failure must be loud:** scripts return non-zero from `main()` on error so the workflow
  goes red. Retry only transient failures (network errors, timeouts, 429, 5xx) with exponential backoff.
- **Tests never touch the network.** `tests/conftest.py` blocks `requests`. Inject a fake
  session and a no-op `sleep` into `fetch.fetch_payload` / `fetch.main`.
- **Adding a city:** append it to `CITIES` in `common.py`, add a colour in
  `make_chart.CITY_COLORS`, add an entry to the test fixture, and update the README intro.
- Generated files (`data/`, `charts/`, the README AQI section) are written by the workflow.
  Don't hand-edit them.
- Keep the Attribution section in README (CAMS + Open-Meteo, CC BY 4.0). It's a licence
  requirement.
- Bot commits use the message `data: AQI snapshot YYYY-MM-DD`. Use normal descriptive
  messages for code changes.

## Commands

```bash
pip install -r requirements.txt
pytest
python fetch.py && python make_chart.py && python update_readme.py
```
