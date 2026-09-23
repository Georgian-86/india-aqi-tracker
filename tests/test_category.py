import pytest

from common import aqi_category


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
