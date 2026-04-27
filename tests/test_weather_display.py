import os
import sys
import pytest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _make_api_response():
    start = datetime(2024, 4, 27, 0, 0)
    times = [(start + timedelta(hours=i)).strftime('%Y-%m-%dT%H:00') for i in range(168)]
    return {
        'current': {
            'time': '2024-04-27T14:00',
            'temperature_2m': 72.1,
            'apparent_temperature': 68.3,
            'relative_humidity_2m': 62,
            'wind_speed_10m': 8.2,
            'weather_code': 2,
            'is_day': 1,
            'uv_index': 3.0,
            'visibility': 16093.4,
            'dew_point_2m': 55.8,
        },
        'hourly': {
            'time': times,
            'temperature_2m': [60.0 + i * 0.1 for i in range(168)],
            'weather_code': [2] * 168,
            'precipitation_probability': [10] * 168,
            'wind_speed_10m': [8.0] * 168,
        },
        'daily': {
            'time': ['2024-04-27', '2024-04-28', '2024-04-29',
                     '2024-04-30', '2024-05-01', '2024-05-02', '2024-05-03'],
            'temperature_2m_max': [76.0, 70.0, 65.0, 68.0, 73.0, 78.0, 72.0],
            'temperature_2m_min': [58.0, 55.0, 52.0, 54.0, 56.0, 60.0, 58.0],
            'weather_code': [2, 3, 61, 3, 0, 0, 2],
            'precipitation_probability_max': [5, 20, 80, 30, 5, 0, 15],
            'sunrise': ['2024-04-27T06:12'] * 7,
            'sunset': ['2024-04-27T19:48'] * 7,
        },
    }


SAMPLE_RESPONSE = _make_api_response()


def test_parse_weather_current_fields():
    from weather_display import parse_weather
    now = datetime(2024, 4, 27, 14, 30)
    result = parse_weather(SAMPLE_RESPONSE, now=now)

    assert round(result['current']['temperature']) == 72
    assert round(result['current']['feels_like']) == 68
    assert result['current']['humidity'] == 62
    assert result['current']['weather_code'] == 2
    assert result['current']['is_day'] == 1
    assert round(result['current']['visibility_mi']) == 10


def test_parse_weather_hourly_slice():
    from weather_display import parse_weather
    now = datetime(2024, 4, 27, 14, 30)
    result = parse_weather(SAMPLE_RESPONSE, now=now)

    assert len(result['hourly']) == 8
    assert result['hourly'][0]['time'] == '2 PM'
    assert result['hourly'][7]['time'] == '9 PM'


def test_parse_weather_daily_slice():
    from weather_display import parse_weather
    now = datetime(2024, 4, 27, 14, 30)
    result = parse_weather(SAMPLE_RESPONSE, now=now)

    assert len(result['daily']) == 7
    assert result['daily'][0]['day'] == 'Sat'
    assert result['daily'][0]['is_today'] is True
    assert result['daily'][1]['is_today'] is False
    assert result['daily'][0]['high'] == 76.0
    assert result['daily'][0]['precip_pct'] == 5


def test_parse_weather_today_sunrise_sunset():
    from weather_display import parse_weather
    now = datetime(2024, 4, 27, 14, 30)
    result = parse_weather(SAMPLE_RESPONSE, now=now)

    assert result['today']['sunrise'] == '6:12 AM'
    assert result['today']['sunset'] == '7:48 PM'
    assert result['today']['precip_pct'] == 5


# ---------------------------------------------------------------------------
# Icon mapping + descriptions
# ---------------------------------------------------------------------------

def test_get_icon_path_clear_day():
    from weather_display import get_icon_path
    base_dir = os.path.dirname(os.path.dirname(__file__))
    icondir = os.path.join(base_dir, 'images', 'icon')
    path = get_icon_path(0, is_day=1, icon_dir=icondir)
    assert path is not None
    assert path.endswith('01d.png')
    assert os.path.exists(path)


def test_get_icon_path_thunderstorm_night():
    from weather_display import get_icon_path
    base_dir = os.path.dirname(os.path.dirname(__file__))
    icondir = os.path.join(base_dir, 'images', 'icon')
    path = get_icon_path(95, is_day=0, icon_dir=icondir)
    assert path is not None
    assert path.endswith('11n.png')


def test_get_icon_path_unknown_code_returns_default():
    from weather_display import get_icon_path
    base_dir = os.path.dirname(os.path.dirname(__file__))
    icondir = os.path.join(base_dir, 'images', 'icon')
    path = get_icon_path(999, is_day=1, icon_dir=icondir)
    assert path is not None


def test_wmo_description_known():
    from weather_display import wmo_description
    assert wmo_description(0) == 'Clear Sky'
    assert wmo_description(61) == 'Light Rain'
    assert wmo_description(95) == 'Thunderstorm'


def test_wmo_description_unknown():
    from weather_display import wmo_description
    assert wmo_description(999) == 'Unknown'


def test_uv_label():
    from weather_display import uv_label
    assert uv_label(0) == 'Low'
    assert uv_label(3) == 'Mod'
    assert uv_label(6) == 'High'
    assert uv_label(8) == 'V.High'
    assert uv_label(11) == 'Extreme'


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------

def test_fingerprint_is_stable():
    from weather_display import parse_weather, compute_fingerprint
    now = datetime(2024, 4, 27, 14, 30)
    weather = parse_weather(SAMPLE_RESPONSE, now=now)
    assert compute_fingerprint(weather) == compute_fingerprint(weather)


def test_fingerprint_changes_on_temp_change():
    import copy
    from weather_display import parse_weather, compute_fingerprint
    now = datetime(2024, 4, 27, 14, 30)
    weather_a = parse_weather(SAMPLE_RESPONSE, now=now)
    modified = copy.deepcopy(SAMPLE_RESPONSE)
    modified['current']['temperature_2m'] = 85.0
    weather_b = parse_weather(modified, now=now)
    assert compute_fingerprint(weather_a) != compute_fingerprint(weather_b)


def test_fingerprint_changes_on_code_change():
    import copy
    from weather_display import parse_weather, compute_fingerprint
    now = datetime(2024, 4, 27, 14, 30)
    weather_a = parse_weather(SAMPLE_RESPONSE, now=now)
    modified = copy.deepcopy(SAMPLE_RESPONSE)
    modified['current']['weather_code'] = 61
    weather_b = parse_weather(modified, now=now)
    assert compute_fingerprint(weather_a) != compute_fingerprint(weather_b)


# ---------------------------------------------------------------------------
# Weather fetching
# ---------------------------------------------------------------------------

def test_fetch_weather_calls_correct_url(monkeypatch):
    import requests as req
    from weather_display import fetch_weather
    captured = {}

    def mock_get(url, params=None, timeout=None):
        captured['url'] = url
        captured['params'] = params
        class FakeResp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return SAMPLE_RESPONSE
        return FakeResp()

    monkeypatch.setattr(req, 'get', mock_get)
    result = fetch_weather()

    assert captured['url'] == 'https://api.open-meteo.com/v1/forecast'
    assert captured['params']['latitude'] == 40.6734
    assert captured['params']['longitude'] == -73.5132
    assert captured['params']['temperature_unit'] == 'fahrenheit'
    assert 'temperature_2m' in captured['params']['current']
    assert result == SAMPLE_RESPONSE


def test_fetch_weather_raises_on_http_error(monkeypatch):
    import requests as req
    from weather_display import fetch_weather

    def mock_get(url, params=None, timeout=None):
        class FakeResp:
            status_code = 500
            def raise_for_status(self):
                raise req.HTTPError('500 Server Error')
            def json(self): return {}
        return FakeResp()

    monkeypatch.setattr(req, 'get', mock_get)
    with pytest.raises(req.HTTPError):
        fetch_weather()
