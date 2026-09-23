import pytest

from common import aqi_category, naqi, naqi_subindex


@pytest.mark.parametrize(
    "aqi, expected",
    [
        (0, "Good"),
        (50, "Good"),
        (51, "Moderate"),
        (100, "Moderate"),
        (100.4, "Unhealthy for Sensitive Groups"),
        (101, "Unhealthy for Sensitive Groups"),
        (150, "Unhealthy for Sensitive Groups"),
        (151, "Unhealthy"),
        (200, "Unhealthy"),
        (201, "Very Unhealthy"),
        (300, "Very Unhealthy"),
        (301, "Hazardous"),
        (500, "Hazardous"),
        ("168", "Unhealthy"),  # CSV values are strings
        ("", "N/A"),
        (None, "N/A"),
        ("abc", "N/A"),
        (-1, "N/A"),
    ],
)
def test_aqi_category(aqi, expected):
    assert aqi_category(aqi) == expected


# India NAQI (CPCB): band edges from the published table.
@pytest.mark.parametrize(
    "pollutant, conc, expected",
    [
        ("pm2_5", 0, 0), ("pm2_5", 30, 50), ("pm2_5", 60, 100), ("pm2_5", 90, 200),
        ("pm2_5", 120, 300), ("pm2_5", 250, 400), ("pm2_5", 45, 75), ("pm2_5", 75, 150),
        ("pm10", 50, 50), ("pm10", 100, 100), ("pm10", 250, 200), ("pm10", 350, 300),
        ("pm10", 430, 400), ("pm10", 175, 150),
    ],
)
def test_naqi_subindex_band_edges(pollutant, conc, expected):
    assert naqi_subindex(pollutant, conc) == pytest.approx(expected)


@pytest.mark.parametrize("pollutant, conc", [("pm2_5", 250.1), ("pm10", 430.1), ("pm10", 900)])
def test_naqi_subindex_severe_has_no_number(pollutant, conc):
    assert naqi_subindex(pollutant, conc) is None


def test_naqi_negative_concentration_rejected():
    with pytest.raises(ValueError):
        naqi_subindex("pm2_5", -1)


@pytest.mark.parametrize(
    "pm25, pm10, expected",
    [
        ("68.8", "129.9", "Moderate"),  # real Delhi 2026-09-22: US AQI 172 "Unhealthy"
        ("24.5", "32.0", "Good"),  # real Mumbai 2026-09-22: US AQI 96 "Moderate"
        ("50", "", "Satisfactory"),  # PM10 missing: PM2.5 alone
        ("", "300", "Poor"),
        ("100", "500", "Severe"),  # PM10 Severe dominates
        ("", "", "N/A"),
        (None, None, "N/A"),
    ],
)
def test_naqi_takes_worse_pollutant(pm25, pm10, expected):
    assert naqi(pm25, pm10).category == expected


@pytest.mark.parametrize(
    "pollutant, conc, expected",
    [
        ("no2", 40, 50), ("no2", 80, 100), ("no2", 180, 200), ("no2", 280, 300),
        ("no2", 400, 400), ("o3_8h", 50, 50), ("o3_8h", 100, 100), ("o3_8h", 168, 200),
        ("o3_8h", 208, 300), ("o3_8h", 748, 400),
    ],
)
def test_naqi_gas_band_edges(pollutant, conc, expected):
    assert naqi_subindex(pollutant, conc) == pytest.approx(expected)


def test_naqi_ozone_can_be_prominent():
    # Chennai-like day: clean PM, afternoon ozone high enough to dominate.
    result = naqi("17.0", "18.3", "20.0", "120.0")
    assert result.prominent == "O₃" and result.category == "Moderate"
    assert result.index == pytest.approx(100 + 20 * 100 / 68)
    assert result.complete


def test_naqi_reports_prominent_pm():
    result = naqi("68.8", "129.9", "40.0", "60.0")
    assert (result.prominent, result.category, result.pollutants) == ("PM2.5", "Moderate", 4)


def test_naqi_completeness_rule():
    assert not naqi("20", "30").complete  # 2 pollutants
    assert naqi("20", "30", "10").complete  # 3, including PM
    # Gases alone can't make an AQI: PM is required.
    assert naqi(None, "", "300", "300").category == "N/A"


def test_naqi_severe_names_the_pollutant():
    result = naqi("20", "30", "20", "800")
    assert (result.index, result.category, result.prominent) == (None, "Severe", "O₃")
