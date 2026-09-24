from datetime import date, timedelta

import pytest

import forecast_skill
import update_readme
from common import CITIES

DELHI, MUMBAI = CITIES[0][0], CITIES[1][0]
K = forecast_skill.MIN_PAIRS


def day(i):
    return (date(2026, 9, 1) + timedelta(days=i)).isoformat()


def fc(d, city, mean):
    return {"date": d, "city": city, "issued": "", "us_aqi_mean": str(mean), "us_aqi_max": "",
            "pm2_5_mean": "", "pm10_mean": "", "fetched_at_utc": "x"}


def actual(d, city, mean):
    return {"date": d, "city": city, "hours": "24", "us_aqi_mean": str(mean),
            "us_aqi_max": "", "pm2_5_mean": "", "pm10_mean": "", "fetched_at_utc": "x"}


def test_pairs_only_days_with_both():
    forecasts = [fc(day(0), DELHI, 150), fc(day(1), DELHI, 160), fc(day(2), DELHI, "")]
    actuals = [actual(day(0), DELHI, 140), actual(day(2), DELHI, 120)]
    assert forecast_skill.pairs(forecasts, actuals) == [(day(0), DELHI, 150.0, 140.0)]


def test_skill_mae_bias_and_hits():
    # Delhi: forecast +20 on even days, -10 on odd days; categories straddle 150/151.
    forecasts, actuals = [], []
    for i in range(K + 1):
        err = 20 if i % 2 == 0 else -10
        forecasts.append(fc(day(i), DELHI, 140 + err))
        actuals.append(actual(day(i), DELHI, 140))
    start, end, [s] = forecast_skill.skill(forecasts, actuals)
    assert (s.city, s.pairs) == (DELHI, K + 1)
    evens = (K + 2) // 2
    odds = (K + 1) - evens
    assert s.mae == pytest.approx((20 * evens + 10 * odds) / (K + 1))
    assert s.bias == pytest.approx((20 * evens - 10 * odds) / (K + 1))
    # 160 is "Unhealthy" vs actual 140 "USG"; 130 is also USG: only odd days hit.
    assert s.category_hits == odds
    assert end == day(K)


def test_skill_needs_min_pairs_and_window():
    forecasts = [fc(day(i), DELHI, 100) for i in range(K - 1)]
    actuals = [actual(day(i), DELHI, 100) for i in range(K - 1)]
    assert forecast_skill.skill(forecasts, actuals) is None
    # Enough pairs, but most fall outside a 3-day window.
    forecasts = [fc(day(i), DELHI, 100) for i in range(K)]
    actuals = [actual(day(i), DELHI, 100) for i in range(K)]
    assert forecast_skill.skill(forecasts, actuals) is not None
    assert forecast_skill.skill(forecasts, actuals, days=3) is None


def test_readme_table_appears_with_enough_pairs():
    forecasts = [fc(day(i), c, 70) for i in range(K) for c in (DELHI, MUMBAI)]
    actuals = [actual(day(i), DELHI, 60) for i in range(K)]  # Mumbai has no actuals
    snaps = [{"date": day(K), "city": DELHI, "us_aqi": "100", "pm2_5": "", "pm10": "",
              "no2": "", "o3": "", "fetched_at_utc": f"{day(K)}T03:17:00Z"}]
    section = update_readme.render_section(snaps, actuals, forecast_rows=forecasts)
    start = (date.fromisoformat(day(K - 1)) - timedelta(days=forecast_skill.WINDOW_DAYS - 1))
    assert f"**Forecast check** ({start.isoformat()} to {day(K - 1)})" in section
    assert f"| {DELHI} | {K} | 10 | +10 | 100% |" in section
    assert f"| {MUMBAI} |" not in section.split("**Forecast check**")[1].split("<sub>")[0]
    assert "not accuracy against ground stations" in section


def test_readme_table_absent_without_pairs():
    snaps = [{"date": day(0), "city": DELHI, "us_aqi": "100", "pm2_5": "", "pm10": "",
              "no2": "", "o3": "", "fetched_at_utc": f"{day(0)}T03:17:00Z"}]
    assert "Forecast check" not in update_readme.render_section(snaps, [], forecast_rows=[])
