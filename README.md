# india-aqi-tracker

[![Daily AQI snapshot](https://github.com/Georgian-86/india-aqi-tracker/actions/workflows/daily.yml/badge.svg)](https://github.com/Georgian-86/india-aqi-tracker/actions/workflows/daily.yml)
[![CI](https://github.com/Georgian-86/india-aqi-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/Georgian-86/india-aqi-tracker/actions/workflows/ci.yml)

A [git scraping](https://simonwillison.net/2020/Oct/9/git-scraping/) project that records the
air quality of eight Indian cities, **Delhi, Mumbai, Bengaluru, Kolkata, Chennai, Hyderabad,
Pune and Ahmedabad**, once a day and commits the result to this repository. The git history *is* the database.

## Today's air quality

<!-- AQI:START -->
**Latest snapshot: 2026-09-23** (fetched 22:50 IST · 1 day collected)

| City | US AQI | Category | vs prev. | PM2.5 (µg/m³) | PM10 (µg/m³) | NO₂ (µg/m³) | O₃ (µg/m³) |
|---|--:|---|:-:|--:|--:|--:|--:|
| Delhi | 179 | 🔴 Unhealthy | – | 99.7 | 111.3 | 60.2 | 73 |
| Mumbai | 89 | 🟡 Moderate | – | 34.7 | 46.7 | 16 | 78 |
| Bengaluru | 55 | 🟡 Moderate | – | 16.6 | 22.8 | 14.5 | 64 |
| Kolkata | 33 | 🟢 Good | – | 8.4 | 9.2 | 9.2 | 45 |
| Chennai | 64 | 🟡 Moderate | – | 14.5 | 16 | 24.7 | 50 |
| Hyderabad | 75 | 🟡 Moderate | – | 20 | 20.6 | 7.7 | 97 |
| Pune | 99 | 🟡 Moderate | – | 30 | 30.9 | 17 | 98 |
| Ahmedabad | 98 | 🟡 Moderate | – | 36.6 | 44.5 | 46.4 | 37 |

<sub>vs prev.: change since the previous snapshot; “–” when there is none or the two were taken more than 3 h apart in time of day (AQI has a daily cycle).</sub>

**Full day 2026-09-22** (mean of 24 hourly values — comparable across days, unlike the single snapshot above)

| City | Mean AQI | Category | Peak AQI | 7-day mean | Mean PM2.5 (µg/m³) | India AQI¹ |
|---|--:|---|--:|--:|--:|---|
| Delhi | 172 | 🔴 Unhealthy | 206 | 157 | 68.8 | 129 Moderate · PM2.5 |
| Mumbai | 96 | 🟡 Moderate | 130 | 76 | 24.5 | 41 Good · PM2.5 |
| Bengaluru | 49 | 🟢 Good | 53 | 56 | 10.5 | 19 Good · NO₂ |
| Kolkata | 64 | 🟡 Moderate | 72 | 104 | 10.1 | 17 Good · PM2.5 |
| Chennai | 73 | 🟡 Moderate | 84 | 93 | 17 | 28 Good · PM2.5 |
| Hyderabad | 98 | 🟡 Moderate | 103 | 84 | 34.8 | 58 Satisfactory · PM2.5 |
| Pune | 76 | 🟡 Moderate | 93 | 55 | 19.1 | 32 Good · PM2.5 |
| Ahmedabad | 115 | 🟠 Unhealthy for Sensitive Groups | 157 | 73 | 39 | 65 Satisfactory · PM2.5 |

<sub>¹ India's National AQI (CPCB) scale: Good ≤ 50 · Satisfactory ≤ 100 · Moderate ≤ 200 · Poor ≤ 300 · Very Poor ≤ 400 · Severe. Computed from the day's mean PM2.5, PM10 and NO₂ (3 of CPCB's 8 pollutants, its minimum), labelled with the pollutant that sets it. ² marks a day with fewer than 3. Ozone is left out: the CAMS model's surface ozone runs far above ground measurements over India, and would make O₃ the main pollutant almost every day. The India figure often reads better than the US one because US breakpoints are stricter (PM2.5 is "Good" only up to 9 µg/m³ in the US, vs 30 in India).</sub>

**Health (CPCB):**
- **Delhi**, Moderate: May cause breathing discomfort to people with lung disease such as asthma, and discomfort to people with heart disease, children and older adults.

**Last 30 days** (2026-08-24 to 2026-09-22, full-day means · 30 days of data): days in each category

| City | 🟢 Good | 🟡 Moderate | 🟠 USG | 🔴 Unhealthy | 🟣 V. Unhealthy | 🟤 Hazardous | Mean | Worst day |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| Delhi | · | 5 | 7 | 14 | 2 | 2 | 162 | 352 on 2026-08-29 |
| Mumbai | · | 29 | 1 | · | · | · | 63 | 110 on 2026-09-21 |
| Bengaluru | 13 | 17 | · | · | · | · | 52 | 80 on 2026-09-15 |
| Kolkata | 1 | 20 | 8 | 1 | · | · | 87 | 164 on 2026-09-19 |
| Chennai | · | 29 | 1 | · | · | · | 77 | 108 on 2026-09-17 |
| Hyderabad | 1 | 29 | · | · | · | · | 70 | 98 on 2026-09-22 |
| Pune | 21 | 9 | · | · | · | · | 44 | 76 on 2026-09-21 |
| Ahmedabad | 1 | 28 | 1 | · | · | · | 70 | 115 on 2026-09-22 |

**Last 30 days on India's scale** (2026-08-24 to 2026-09-22, CPCB categories from PM2.5, PM10 and NO₂): days in each category, and which pollutant set the index how often

| City | Good | Satisfactory | Moderate | Poor | Very Poor | Severe | Main pollutants |
|---|--:|--:|--:|--:|--:|--:|---|
| Delhi | 4 | 9 | 11 | 2 | 3 | 1 | PM2.5 22 · PM10 8 |
| Mumbai | 27 | 3 | · | · | · | · | PM10 24 · PM2.5 6 |
| Bengaluru | 30 | · | · | · | · | · | NO₂ 14 · PM10 8 · PM2.5 8 |
| Kolkata | 20 | 9 | 1 | · | · | · | PM2.5 30 |
| Chennai | 30 | · | · | · | · | · | PM2.5 30 |
| Hyderabad | 27 | 3 | · | · | · | · | PM2.5 25 · PM10 5 |
| Pune | 30 | · | · | · | · | · | PM2.5 14 · PM10 12 · NO₂ 4 |
| Ahmedabad | 25 | 5 | · | · | · | · | PM10 19 · PM2.5 8 · NO₂ 3 |

![US AQI trend by city](https://raw.githubusercontent.com/Georgian-86/india-aqi-tracker/charts/aqi_trend.png)
<!-- AQI:END -->

AQI categories follow the US EPA scale:
🟢 Good (0–50) · 🟡 Moderate (51–100) · 🟠 Unhealthy for Sensitive Groups (101–150) ·
🔴 Unhealthy (151–200) · 🟣 Very Unhealthy (201–300) · 🟤 Hazardous (301+).

## How it works

Every day at **03:17 UTC (08:47 IST)** the GitHub Actions workflow
[`.github/workflows/daily.yml`](.github/workflows/daily.yml):

1. runs the test suite (`pytest`, no network);
2. runs **`fetch.py`**, which makes a *single* request to the
   [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api) with all eight
   cities' coordinates, asks for the current `us_aqi`, `pm2_5`, `pm10`, `nitrogen_dioxide` and
   `ozone`, and appends one row per city to [`data/aqi.csv`](data/aqi.csv).
   The same request also returns **yesterday's 24 hourly values**. From these it computes
   full-day statistics (mean and peak AQI, mean PM2.5 and PM10) into
   [`data/aqi_daily.csv`](data/aqi_daily.csv). Unlike the snapshot, these don't depend on
   the time of day the job ran.
   Rows are keyed by `(date, city)` using the IST date, so re-running on the same day never
   duplicates data. Network errors, timeouts, HTTP 429 and 5xx are retried with exponential
   backoff. The run fails (goes red) instead of recording something wrong if the retries run
   out, the data is more than 6 hours old, the locations come back in an unexpected order, or
   a city has no AQI value. In the last case the other cities are still saved;
3. runs **`make_chart.py`** to redraw the chart, then publishes it to the
   [`charts`](../../tree/charts) branch. That branch holds a single commit that is replaced on
   every run, so a new image each day doesn't bloat the repository's history. The
   chart plots the full-day mean AQI, falling back to the single snapshot only when no
   full-day data exists yet. If a rare extreme (such as a dust storm pushing Delhi past 600)
   would squash the other lines, the y-axis is capped at max(300, 95th percentile × 1.15).
   Clipped runs are marked ▲ with their peak value;
4. runs **`update_readme.py`** to rewrite the section between the `AQI:START` / `AQI:END`
   markers above: the latest snapshot, the latest full day with a 7-day mean and **CPCB
   health advice** for any city at Moderate or worse on India's scale, and **last 30 days**
   tables on both scales. If today's snapshot is missing (for example, the fetch failed), a
   ⚠️ warning appears at the top of the section, because the README step runs even when the
   fetch fails;
5. commits `data: AQI snapshot YYYY-MM-DD` and pushes to `main`, but only if something
   actually changed.
6. runs **`alerts.py`**, which manages **GitHub issues for severe episodes**. It opens one
   (label `aqi-alert`) when a city's full-day mean reaches **Very Unhealthy (≥ 201)**,
   comments once per day while it lasts, and closes it once the mean drops **below 151**.
   The gap between the two thresholds keeps an issue from flapping open and closed. Replayed
   over the backfilled June–September data, this would have opened 3 issues, all for Delhi.
   Watch the repo (Custom → Issues) to be notified.

A **backup run at 06:17 UTC (11:47 IST)** does the same thing. It adds nothing if the morning
run succeeded, and fills in any city the morning run missed (for example, if GitHub skipped
the scheduled run, which it sometimes does under load).

You can also trigger a run by hand from the **Actions** tab (`workflow_dispatch`). Note that
the first run of an IST day is the one that counts: a manual run at 22:00 records a 22:00
reading for that date, and the next morning's run won't replace it. The README shows the
actual fetch time.

### Backfilling history

Open-Meteo serves up to 92 days of past hourly data. To fill `aqi_daily.csv` with that history
in one go, run the workflow manually (**Actions → Daily AQI snapshot → Run workflow**) with
`past_days` set to `92`, or run `python fetch.py --past-days 92` locally. Days already stored
are left untouched, so running it again is harmless. The snapshot CSV can't be backfilled,
because the API only has a "current" value for now.

A separate [CI workflow](.github/workflows/ci.yml) runs `ruff` and `pytest` on every pull
request and push to `main`. Dependencies are pinned exactly in `requirements.txt`, and
Dependabot proposes upgrades monthly.

### Data format

`data/aqi.csv`:

| column | meaning |
|---|---|
| `date` | local date in Asia/Kolkata (from the API's `current.time`) |
| `city` | Delhi, Mumbai, Bengaluru, Kolkata, Chennai, Hyderabad, Pune or Ahmedabad. The last three were added on 2026-09-23: their full-day history was backfilled 92 days, but their snapshots start that day |
| `us_aqi` | US AQI (0–500) |
| `pm2_5`, `pm10` | particulate matter, µg/m³ |
| `no2` | nitrogen dioxide, µg/m³ |
| `o3` | ozone, µg/m³ |
| `fetched_at_utc` | when the snapshot was taken, ISO-8601 UTC |

`data/aqi_daily.csv` has one row per city per **completed** IST day. Rows are in the order
they were added (a backfill appends older days after newer ones), so sort by `date` when
reading:

| column | meaning |
|---|---|
| `date` | the IST day the statistics cover |
| `city` | city name |
| `hours` | how many of the 24 hourly values were available (at least 20 are required) |
| `us_aqi_mean`, `us_aqi_max` | mean and peak of the hourly US AQI |
| `pm2_5_mean`, `pm10_mean` | mean concentration, µg/m³ |
| `fetched_at_utc` | when it was fetched |

`data/aqi_daily_gases.csv` holds gas statistics for the same days. It's a separate file so
the append-only `aqi_daily.csv` never needs its header rewritten:

| column | meaning |
|---|---|
| `date`, `city` | same key as `aqi_daily.csv` |
| `no2_mean` | 24-hour mean NO₂, µg/m³ (blank if fewer than 20 hourly values) |
| `o3_max8h` | highest 8-hour mean O₃ within the day, µg/m³; only windows with all 8 hours count |
| `fetched_at_utc` | when it was fetched |

### Caveats

- **Two AQI scales.** The main figures use the **US EPA AQI** (as reported by Open-Meteo). The
  full-day table also shows **India's National AQI** (CPCB), which uses different breakpoints
  and categories (Good, Satisfactory, Moderate, Poor, Very Poor, Severe). On 22 Sep 2026,
  Delhi was US 172 "Unhealthy" but India 129 "Moderate". The gap has two causes: the US
  breakpoints are stricter (PM2.5 is "Good" only up to 9 µg/m³, vs 30 in India), and the US
  figure also includes ozone and NO₂. The India figure uses PM2.5, PM10 and NO₂ (24-hour
  means), which is CPCB's minimum of three pollutants including PM, and names the pollutant
  that sets it. A day with fewer than 3 is marked ². "Severe (401+)" has no number, because
  CPCB publishes no upper concentration for that band.
- **Does the ozone bias also skew the US AQI?** Mostly not. Over the 92 backfilled days, the US
  AQI matches a PM-only US AQI (median gap 0 to +6 per city). Delhi's larger gaps are mostly
  dust days, where averaging spiky hourly values raises the daily mean. Ozone added 20–30
  points on only 5 Delhi days, and never enough to trigger an alert.
- **Ozone is recorded but not used in the India AQI.** Compared with ground stations across
  India, CAMS surface ozone has been found to run 42–108 µg/m³ above observations, where
  observed daily means are about 7–58 µg/m³
  ([Springer, 2025](https://link.springer.com/article/10.1007/s42865-025-00109-x)).
  Including it made O₃ the "main pollutant" in every city on almost every day, even during
  the monsoon, and pushed Delhi to "Very Poor" on a day PM put at "Moderate". The O₃ column
  in `aqi_daily_gases.csv` is kept for reference only. Treat it as heavily biased.

- Values are **model estimates** from the CAMS global forecast (~40 km grid), not readings
  from ground monitoring stations. They are good for trends and comparisons but can differ
  from official CPCB station readings.
- Each `aqi.csv` row is **one instantaneous reading**. Pollution follows a daily cycle (in
  winter it's usually worst in the early morning), so snapshots are only comparable across
  days when taken at a similar time. That's why the README's "vs prev." column only compares
  readings taken within 3 hours of the same time of day. For trends, use `aqi_daily.csv`.
- Open-Meteo extends US AQI above 500, the official top of the scale ("Beyond the AQI"), so
  dust-storm days can show values like 620. They're still categorised as Hazardous.
- `us_aqi_mean` is the mean of Open-Meteo's hourly US AQI values. This is not the same as
  the EPA's official daily AQI, which is computed from 24-hour mean concentrations.

## Running locally

Requires Python 3.12.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest                      # offline tests (API is mocked)
ruff check .                # lint (pip install ruff)
python fetch.py             # real API call → data/aqi.csv + data/aqi_daily.csv
python fetch.py --past-days 92   # same, plus daily stats for the last 92 days
python make_chart.py        # → charts/aqi_trend.png (git-ignored; CI publishes it)
python update_readme.py     # → README.md section
```

## Attribution

Air quality data is provided by **[Open-Meteo](https://open-meteo.com/)** under the
[Creative Commons Attribution 4.0 (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
licence. See the [Open-Meteo licence page](https://open-meteo.com/en/license).

Open-Meteo's air quality data is derived from the
**[Copernicus Atmosphere Monitoring Service (CAMS)](https://atmosphere.copernicus.eu/)**:

> Generated using Copernicus Atmosphere Monitoring Service information 2026.
> Neither the European Commission nor ECMWF is responsible for any use that may be made of
> the Copernicus information or data it contains.

The CSV data in this repository is a derived work and is shared under the same CC BY 4.0
terms. Please keep these attributions if you reuse it.
