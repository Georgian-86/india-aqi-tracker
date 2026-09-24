# india-aqi-tracker

[![Daily AQI snapshot](https://github.com/Georgian-86/india-aqi-tracker/actions/workflows/daily.yml/badge.svg)](https://github.com/Georgian-86/india-aqi-tracker/actions/workflows/daily.yml)
[![CI](https://github.com/Georgian-86/india-aqi-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/Georgian-86/india-aqi-tracker/actions/workflows/ci.yml)
[![Latest snapshot](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2FGeorgian-86%2Findia-aqi-tracker%2Fmain%2Fdata%2Flatest.json&query=%24.snapshot.date&label=latest%20snapshot&color=blue)](data/latest.json)

A [git scraping](https://simonwillison.net/2020/Oct/9/git-scraping/) project that records the
air quality of eight Indian cities, **Delhi, Mumbai, Bengaluru, Kolkata, Chennai, Hyderabad,
Pune and Ahmedabad**, once a day and commits the result to this repository. The git history *is* the database.

## Today's air quality

<!-- AQI:START -->
**Right now (US AQI):** worst **Delhi** 159 🔴 Unhealthy · cleanest **Kolkata** 31 🟢 Good · 1 of 8 cities Unhealthy or worse.

**Forecast for 2026-09-25** (CAMS, full-day mean US AQI): Delhi 109 🟠 · Mumbai 84 🟡 · Bengaluru 34 🟢 · Kolkata 36 🟢 · Chennai 66 🟡 · Hyderabad 77 🟡 · Pune 74 🟡 · Ahmedabad 70 🟡

**Category changes in the last 24 h:** none.

**Latest snapshot: 2026-09-24** (fetched 09:43 IST · 2 days collected)

| City | US AQI | Category | vs prev. | PM2.5 (µg/m³) | PM10 (µg/m³) | NO₂ (µg/m³) | O₃ (µg/m³) |
|---|--:|---|:-:|--:|--:|--:|--:|
| Delhi | 159 | 🔴 Unhealthy | – | 32.1 | 52.3 | 20.1 | 116 |
| Mumbai | 103 | 🟠 Unhealthy for Sensitive Groups | – | 33.6 | 53.7 | 9.5 | 88 |
| Bengaluru | 55 | 🟡 Moderate | – | 6.1 | 8.3 | 6 | 67 |
| Kolkata | 31 | 🟢 Good | – | 6.1 | 7 | 5.3 | 64 |
| Chennai | 57 | 🟡 Moderate | – | 12.8 | 15.5 | 10.3 | 74 |
| Hyderabad | 80 | 🟡 Moderate | – | 20.7 | 21.1 | 8.5 | 98 |
| Pune | 89 | 🟡 Moderate | – | 30.2 | 34.5 | 8.5 | 102 |
| Ahmedabad | 78 | 🟡 Moderate | – | 20.5 | 34.1 | 9 | 69 |

<sub>vs prev.: change since the previous snapshot; “–” when there is none or the two were taken more than 3 h apart in time of day (AQI has a daily cycle). O₃ is the model's value, which runs well above ground measurements over India (see [Caveats](#caveats)).</sub>

**Full day 2026-09-23** (mean of 24 hourly values — comparable across days, unlike the single snapshot above)

| City | Mean AQI | Category | Peak AQI | 7-day mean | Mean PM2.5 (µg/m³) | India AQI¹ |
|---|--:|---|--:|--:|--:|---|
| Delhi | 167 | 🔴 Unhealthy | 208 | 157 | 70 | 133 Moderate · PM2.5 |
| Mumbai | 85 | 🟡 Moderate | 99 | 80 | 33.2 | 55 Satisfactory · PM2.5 |
| Bengaluru | 54 | 🟡 Moderate | 55 | 54 | 11.9 | 20 Good · PM2.5 |
| Kolkata | 39 | 🟢 Good | 52 | 98 | 5.6 | 9 Good · PM2.5 |
| Chennai | 66 | 🟡 Moderate | 68 | 89 | 14.2 | 24 Good · PM2.5 |
| Hyderabad | 88 | 🟡 Moderate | 99 | 83 | 22.3 | 37 Good · PM2.5 |
| Pune | 80 | 🟡 Moderate | 116 | 60 | 22.9 | 38 Good · PM2.5 |
| Ahmedabad | 96 | 🟡 Moderate | 109 | 79 | 29.5 | 49 Good · PM2.5 |

<sub>¹ India's National AQI (CPCB) scale: Good ≤ 50 · Satisfactory ≤ 100 · Moderate ≤ 200 · Poor ≤ 300 · Very Poor ≤ 400 · Severe. Computed from the day's mean PM2.5, PM10 and NO₂ (3 of CPCB's 8 pollutants, its minimum), labelled with the pollutant that sets it. ² marks a day with fewer than 3. Ozone is left out: the CAMS model's surface ozone runs far above ground measurements over India, and would make O₃ the main pollutant almost every day. The India figure often reads better than the US one because US breakpoints are stricter (PM2.5 is "Good" only up to 9 µg/m³ in the US, vs 30 in India).</sub>

**Health (CPCB):**
- **Delhi**, Moderate: May cause breathing discomfort to people with lung disease such as asthma, and discomfort to people with heart disease, children and older adults.

**Last 30 days** (2026-08-25 to 2026-09-23, full-day means · 30 days of data): days in each category

| City | 🟢 Good | 🟡 Moderate | 🟠 USG | 🔴 Unhealthy | 🟣 V. Unhealthy | 🟤 Hazardous | Mean | Worst day |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| Delhi | · | 5 | 7 | 14 | 2 | 2 | 163 | 352 on 2026-08-29 |
| Mumbai | · | 29 | 1 | · | · | · | 64 | 110 on 2026-09-21 |
| Bengaluru | 12 | 18 | · | · | · | · | 53 | 80 on 2026-09-15 |
| Kolkata | 2 | 19 | 8 | 1 | · | · | 87 | 164 on 2026-09-19 |
| Chennai | · | 29 | 1 | · | · | · | 77 | 108 on 2026-09-17 |
| Hyderabad | 1 | 29 | · | · | · | · | 71 | 98 on 2026-09-22 |
| Pune | 20 | 10 | · | · | · | · | 46 | 80 on 2026-09-23 |
| Ahmedabad | 1 | 28 | 1 | · | · | · | 70 | 115 on 2026-09-22 |

**Last 30 days on India's scale** (2026-08-25 to 2026-09-23, CPCB categories from PM2.5, PM10 and NO₂): days in each category, and which pollutant set the index how often

| City | Good | Satisfactory | Moderate | Poor | Very Poor | Severe | Main pollutants |
|---|--:|--:|--:|--:|--:|--:|---|
| Delhi | 4 | 9 | 11 | 2 | 3 | 1 | PM2.5 22 · PM10 8 |
| Mumbai | 26 | 4 | · | · | · | · | PM10 23 · PM2.5 7 |
| Bengaluru | 30 | · | · | · | · | · | NO₂ 13 · PM2.5 9 · PM10 8 |
| Kolkata | 20 | 9 | 1 | · | · | · | PM2.5 30 |
| Chennai | 30 | · | · | · | · | · | PM2.5 30 |
| Hyderabad | 27 | 3 | · | · | · | · | PM2.5 25 · PM10 5 |
| Pune | 30 | · | · | · | · | · | PM2.5 15 · PM10 11 · NO₂ 4 |
| Ahmedabad | 26 | 4 | · | · | · | · | PM10 18 · PM2.5 9 · NO₂ 3 |

**Time of day** (2026-08-25 to 2026-09-23, IST): the 3-hour stretches with the lowest and highest mean PM2.5

| City | Cleanest (µg/m³) | Worst (µg/m³) | Worst ÷ cleanest |
|---|---|---|--:|
| Delhi | 15:00–18:00 (53) | 22:00–01:00 (80) | 1.5× |
| Mumbai | 04:00–07:00 (14) | 12:00–15:00 (18) | 1.3× |
| Bengaluru | 04:00–07:00 (9) | 19:00–22:00 (18) | 2.1× |
| Kolkata | 14:00–17:00 (22) | 21:00–00:00 (32) | 1.4× |
| Chennai | 05:00–08:00 (15) | 18:00–21:00 (23) | 1.5× |
| Hyderabad | 14:00–17:00 (15) | 21:00–00:00 (29) | 1.9× |
| Pune | 05:00–08:00 (7) | 20:00–23:00 (13) | 1.8× |
| Ahmedabad | 06:00–09:00 (14) | 19:00–22:00 (27) | 1.9× |

<sub>From CAMS hourly PM2.5: the model's daily cycle (night-time inversions, traffic), not street-level readings. Hourly US AQI isn't used here: it's built from 24-hour PM averages, so it barely changes within a day.</sub>

![US AQI trend by city](https://raw.githubusercontent.com/Georgian-86/india-aqi-tracker/charts/aqi_trend.png)

**Monthly reports:** [Aug 2026](reports/2026-08.md) · [Jul 2026](reports/2026-07.md) · [Jun 2026](reports/2026-06.md) · [all 49 by year](reports/)
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
   the time of day the job ran. It also returns **tomorrow's 24 forecast hours**. The same
   statistics computed from these go to [`data/aqi_forecast.csv`](data/aqi_forecast.csv),
   and a one-line forecast appears above the snapshot table. A forecast that can't be computed
   only prints a warning; it doesn't fail the run.
   Rows are keyed by `(date, city)` using the IST date, so re-running on the same day never
   duplicates data. Network errors, timeouts, HTTP 429 and 5xx are retried with exponential
   backoff. The run fails (goes red) instead of recording something wrong if the retries run
   out, the data is more than 6 hours old, the locations come back in an unexpected order, or
   a city has no AQI value. In the last case the other cities are still saved;
3. runs **`make_chart.py`** to redraw the chart, then publishes it to the
   [`charts`](../../tree/charts) branch. That branch holds a single commit that is replaced on
   every run, so a new image each day doesn't bloat the repository's history. The
   chart has one panel per city for the last 12 months, with shared axes so levels compare
   directly: daily full-day means as a faint line, and a bold 7-day mean. It falls back to the
   single snapshot only when no full-day data exists yet. So that a dust storm pushing Delhi
   past 600 doesn't flatten every panel, the shared axis is capped at max(300, 95th
   percentile × 1.15), and a panel with higher values notes its peak;
4. runs **`report.py`**, which writes a **monthly report** to [`reports/`](reports/) once a
   month completes (a city ranking, days per India AQI category, and the main pollutants).
   Reports are written once and never rewritten, like the CSVs. Months with fewer than 20
   days of data are skipped. It also regenerates [`reports/README.md`](reports/README.md),
   an index with one row per year; the section above links only the latest 3 reports;
5. runs **`update_readme.py`** to rewrite the section between the `AQI:START` / `AQI:END`
   markers above: a one-line headline (worst and cleanest city right now, and how many are
   Unhealthy or worse), the latest snapshot, the latest full day with a 7-day mean and **CPCB
   health advice** for any city at Moderate or worse on India's scale, and **last 30 days**
   tables on both scales. If today's snapshot is missing (for example, the fetch failed), a
   ⚠️ warning appears at the top of the section, because the README step runs even when the
   fetch fails. Then **`latest_json.py`** writes the same latest numbers to
   [`data/latest.json`](data/latest.json) for other programs (see [Data format](#data-format));
6. commits `data: AQI snapshot YYYY-MM-DD` and pushes to `main`, but only if something
   actually changed.
7. runs **`alerts.py`**, which manages **GitHub issues for severe episodes**. It opens one
   (label `aqi-alert`) when a city's full-day mean is **Hazardous (≥ 301) for 3 days in a
   row**, comments once per day while it lasts, and closes it once the mean drops **below
   201**. The gap between the two thresholds keeps an issue from flapping open and closed.
   The thresholds were chosen by replaying 572 days of real data (Feb 2025 to Sep 2026):
   about 7 issues a year, all Delhi, open about 11% of the time, with a median episode of 3
   days. A lower threshold would have kept Delhi's alert open more than half the year.
   Watch the repo (Custom → Issues) to be notified.

A second, lighter workflow, [`events.yml`](.github/workflows/events.yml), runs **every 3
hours** (at :45 UTC). **`events.py`** reads the current US AQI for all cities and logs a row to
[`data/aqi_events.csv`](data/aqi_events.csv) only when a city's **category has changed**
since its last logged one, for example Delhi going from Unhealthy to Very Unhealthy. It
commits only when something changed, so the history follows the air: nothing on a steady
day, several commits when smog or dust moves through. A change counts only once the reading
is at least 10 points past the edge of the old category, so a city hovering around a
boundary (say 98–103) doesn't flip back and forth. The daily README lists the changes from
the 24 hours before its snapshot. Both workflows share a concurrency group, so they never
push at the same time.

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

To go **further back than 92 days**, fill in the workflow's `since` input (e.g. `2022-01-01`)
or run `python backfill.py --since 2022-01-01`. It walks backwards from the oldest stored day
in 60-day requests, and stops by itself where the CAMS archive ends: when the API rejects a
range, or returns no data for any city. Older months then get their monthly reports on the
next run. The chart always shows the last 365 days; older history lives in the reports.

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

`data/aqi_hourly.csv` keeps the **hourly** values behind each completed day (`date`, `hour`
0–23 IST, `city`, `us_aqi`, `pm2_5`, `pm10`). It adds about 190 rows a day and is keyed on
`(date, hour, city)`. It has no `fetched_at_utc` column: that would double the file's size,
and `aqi_daily.csv` records the fetch time for the same day. The README uses it for a
**time of day** table (`diurnal.py`): for each city, the 3-hour stretches with the lowest
and highest mean **PM2.5** over the last 30 days. It uses PM2.5, not the hourly US AQI,
because Open-Meteo builds the hourly US AQI from 24-hour PM averages and 8-hour ozone
averages, as the EPA defines it. That makes it nearly flat within a day, with an afternoon
ozone bump. On real data it put Delhi's worst hours at 17:00–20:00, while hourly PM2.5 is
worst around 22:00–01:00 and about 1.5× the afternoon low. A city appears once every hour has at least
14 days of data. The profile is the CAMS model's daily cycle (night-time inversions,
traffic peaks), not street-level readings.

`data/latest.json` is for programs that just want today's numbers. It holds the latest
snapshot and the latest full day for every city, with categories on both scales, and is
rewritten on each run (it's the only file in `data/` that isn't append-only). Missing
values are `null`, and so is the India AQI `index` on a Severe day, since CPCB's scale has
no number above 500. Check `snapshot.date` to see how fresh it is. The raw URL is
`https://raw.githubusercontent.com/Georgian-86/india-aqi-tracker/main/data/latest.json`.
The "latest snapshot" badge at the top of this page reads its date from that file each
time the page is viewed. So unlike the README's own staleness warning, which is written
by the workflow, it also shows when the workflow has stopped running altogether (for
example, a delayed or disabled schedule).
The `schema_version` field is bumped only on breaking changes.

`data/aqi_forecast.csv` records the CAMS **forecast** for the day after each snapshot, with
the same statistics as `aqi_daily.csv`. It is kept so forecasts can later be checked against
what the model reported for the day once it had passed:

| column | meaning |
|---|---|
| `date` | the IST day being forecast |
| `city` | city name |
| `issued` | the IST day the forecast was fetched (the day before `date`) |
| `us_aqi_mean`, `us_aqi_max` | forecast mean and peak hourly US AQI |
| `pm2_5_mean`, `pm10_mean` | forecast mean concentration, µg/m³ |
| `fetched_at_utc` | when it was fetched |

The first forecast stored for a `(date, city)` is kept, so the backup run later the same
morning doesn't overwrite it.

Once a city has at least 7 forecast days with a matching actual day, the README adds a
**forecast check** table for the last 30 days (`forecast_skill.py`). It shows the mean
error and bias of the forecast full-day US AQI, and how often the forecast got the
category right. Both sides are CAMS output: the "actual" is the model's hourly values
for the day, fetched after it ended. So the table shows how much the day-ahead forecast
moved, not how accurate it is against ground stations.

`data/aqi_events.csv` is the category-change log written by `events.py`. A city's first row
has an empty `from_category` and just records its starting state:

| column | meaning |
|---|---|
| `time_ist` | when the reading applies, IST (`YYYY-MM-DDTHH:MM`, from the API's `current.time`) |
| `city` | city name |
| `from_category`, `to_category` | US AQI category before and after |
| `us_aqi`, `pm2_5`, `pm10` | the reading that triggered the change |
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
- **Don't read long-term trends from this data: the model changes over time.** The backfilled
  history (August 2022 onward) comes from CAMS forecasts, whose model is upgraded
  periodically, and two step changes show up in it:
  - **NO₂, all cities, end of June 2023:** January–June 2023 averages about 2× the same
    months of 2024 across the cities (month-on-month ratios 0.43–0.56). From July 2023 the
    year-on-year ratio is about 1. Real urban NO₂ doesn't halve overnight in eight cities.
  - **PM10, Delhi's dust season, from 2025:** March–June PM10 goes from about 80–100 µg/m³
    (2023) to 300–490 (2025–26), while Delhi's October–February PM10 stays flat (about
    100–180) and no other city shows anything similar.

  Comparisons within a season of the same year are fine. Year-over-year comparisons, above
  all Delhi's pre-monsoon US AQI, are not. That's why this project has no year-over-year
  table. The monthly reports are accurate descriptions of what the model said at the time.

  New steps are caught automatically. **`drift.py`** compares each month with the same
  month a year earlier. It flags a pollutant when the median city moves by more than ×1.67
  (a model change moves every city at once, and real air doesn't), or when one city moves by
  more than ×3. Each new monthly report includes this as a "Data consistency" section.
  Run `python drift.py` to scan the whole history. On the backfill it flags exactly the two
  steps above, and never flags PM2.5 or US AQI.
- **Delhi's worst months in this data are March–June, not winter.** Monthly means peak
  pre-monsoon (up to ~380 in May 2026), driven by PM10 (dust), while winter months are ~185–
  205. Ground stations usually show the reverse, with PM2.5 smog in November–January as
  Delhi's worst. So CAMS likely overestimates dust. Treat dust-season values as upper
  bounds, especially for Delhi and Ahmedabad.
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
