# WeatherDisplay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace TideTracker.py with a focused weather-only e-ink display fetching from Open-Meteo, refreshing only when weather data changes.

**Architecture:** Single `weather_display.py` with pure functions for parsing, fingerprinting, rendering, and writing. A 30-minute poll loop compares a fingerprint of key weather fields and only redraws the e-ink display when the data changes.

**Tech Stack:** Python 3, requests, Pillow (PIL), Open-Meteo API (free, no auth), Waveshare epd7in5_V2 driver

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `weather_display.py` | Create | All logic: fetch, parse, fingerprint, render, main loop |
| `config.py` | Modify | Strip to location constants only |
| `tests/test_weather_display.py` | Create | Unit tests for all pure functions |
| `TideTracker.py` | Leave | Not deleted, not imported |
| `owlet_monitor.py` | Leave | Not deleted, not imported |
| `lib/waveshare_epd/epd7in5_V2.py` | Leave | Unchanged e-ink driver |
| `images/icon/*.png` | Leave | Reused OWM icon PNGs |
| `font/Font.ttc` | Leave | Reused font |

---

## Layout Reference (800×480)

```
x=0                  x=305           x=800
┌────────────────────┬───────────────────────┐  y=0
│   LEFT PANEL       │   HOURLY PANEL        │
│   (w=304)          │   (w=493)             │
│                    │                       │
│ Location           │  NEXT 8 HOURS         │
│ Description        │  2PM 3PM ... 9PM      │
│ [icon] TEMP°F      │  [i] [i] ... [i]      │
│                    │  74° 73° ... 62°      │
│ Feels like  68°F   │  5%  10% ... 15%      │
│ Wind        8 mph  │  6   7  ...  8mph     │
│ Humidity    62%    ├───────────────────────┤  y=157
│ High/Low 76°/58°   │ UV:3 Vis:10 Dew:56°  │
│ Precip      10%    │ ↑6:12AM    ↓7:48PM   │
│                    │                       │
│ Mon Apr 27 2:14PM  │                       │
├────────────────────┴───────────────────────┤  y=293
│  7-DAY FORECAST (full width)               │
│  Mon  Tue  Wed  Thu  Fri  Sat  Sun         │
│  [i]  [i]  [i]  [i]  [i]  [i]  [i]       │
│  76°  70°  65°  68°  73°  78°  72°        │
│  58°  55°  52°  54°  56°  60°  58°        │
│   5%  20%  80%  30%   5%   0%  15%        │
└────────────────────────────────────────────┘  y=480
```

**Pixel positions:**
- Vertical divider: x=305, y=0 to y=293
- Horizontal divider: y=293, x=0 to x=800
- Hourly/stats divider: y=157, x=307 to x=799
- Hourly columns: cx = 337 + i×61 for i=0..7 → [337, 398, 459, 520, 581, 642, 703, 764]
- Daily columns: cx = 57 + i×114 for i=0..6 → [57, 171, 285, 399, 513, 627, 741]
- Stats item centers: [356, 455, 554, 653, 752] (5 items in right panel)

---

## Task 1: Update config.py

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Overwrite config.py with location-only constants**

```python
LOCATION = 'Wantagh, NY'
LATITUDE = 40.6734
LONGITUDE = -73.5132
```

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "config: strip to weather location constants for Wantagh NY"
```

---

## Task 2: Weather Parsing (TDD)

**Files:**
- Create: `weather_display.py` (initial skeleton + parse_weather)
- Create: `tests/test_weather_display.py`

Open-Meteo returns hourly arrays spanning 7 days (168 entries). `parse_weather` finds the current hour's index, slices 8 hours forward, and structures everything for the renderer.

- [ ] **Step 1: Create the test file with fixture and failing test**

```python
# tests/test_weather_display.py
import os
import sys
import pytest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _make_api_response():
    """Minimal Open-Meteo API response fixture."""
    base = datetime(2024, 4, 27, 0, 0)
    times = [(base.replace(hour=0) if i == 0 else base)
             .__class__(2024, 4, 27 + i // 24, i % 24, 0)
             .strftime('%Y-%m-%dT%H:00')
             for i in range(168)]
    # Simpler: just build the list explicitly
    from datetime import timedelta
    start = datetime(2024, 4, 27, 0, 0)
    times = [(start + timedelta(hours=i)).strftime('%Y-%m-%dT%H:00')
             for i in range(168)]
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
            'visibility': 16093.4,   # 10 miles in meters
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
    # First hour should be 2 PM (index 14 in fixture)
    assert result['hourly'][0]['time'] == '2 PM'
    assert result['hourly'][7]['time'] == '9 PM'


def test_parse_weather_daily_slice():
    from weather_display import parse_weather
    now = datetime(2024, 4, 27, 14, 30)
    result = parse_weather(SAMPLE_RESPONSE, now=now)

    assert len(result['daily']) == 7
    assert result['daily'][0]['day'] == 'Sun'   # Apr 27 2024 is a Saturday... adjust
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
```

> **Note:** `Apr 27 2024` is a Saturday. Update `assert result['daily'][0]['day'] == 'Sun'` to `== 'Sat'` after running and confirming the actual output.

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /Users/nicholascariello/PycharmProjects/TideTracker
python -m pytest tests/test_weather_display.py -v
```

Expected: `ModuleNotFoundError: No module named 'weather_display'`

- [ ] **Step 3: Create weather_display.py with parse_weather**

```python
# weather_display.py
import os
import sys
import time
import hashlib
import logging
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

sys.path.append(os.path.dirname(__file__))
import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

EPD_AVAILABLE = False
try:
    from lib.waveshare_epd import epd7in5_V2
    EPD_AVAILABLE = True
except Exception:
    pass


# ---------------------------------------------------------------------------
# Weather parsing
# ---------------------------------------------------------------------------

def parse_weather(raw, now=None):
    """Parse Open-Meteo API JSON into a structured display dict."""
    if now is None:
        now = datetime.now()

    current_raw = raw['current']
    hourly_raw = raw['hourly']
    daily_raw = raw['daily']

    # Find index of current hour in the hourly array
    current_hour_str = now.strftime('%Y-%m-%dT%H:00')
    try:
        hour_idx = hourly_raw['time'].index(current_hour_str)
    except ValueError:
        hour_idx = 0

    # Slice 8 hours starting from current hour
    hourly = []
    for i in range(hour_idx, min(hour_idx + 8, len(hourly_raw['time']))):
        t = datetime.fromisoformat(hourly_raw['time'][i])
        hourly.append({
            'time': t.strftime('%I %p').lstrip('0'),   # "2 PM"
            'temp': hourly_raw['temperature_2m'][i],
            'weather_code': hourly_raw['weather_code'][i],
            'precip_pct': hourly_raw['precipitation_probability'][i],
            'wind_speed': hourly_raw['wind_speed_10m'][i],
        })

    # 7-day daily forecast
    daily = []
    for i in range(min(7, len(daily_raw['time']))):
        d = datetime.fromisoformat(daily_raw['time'][i])
        daily.append({
            'day': d.strftime('%a'),
            'weather_code': daily_raw['weather_code'][i],
            'high': daily_raw['temperature_2m_max'][i],
            'low': daily_raw['temperature_2m_min'][i],
            'precip_pct': daily_raw['precipitation_probability_max'][i],
            'is_today': i == 0,
        })

    # Sunrise / sunset for today
    sunrise_dt = datetime.fromisoformat(daily_raw['sunrise'][0])
    sunset_dt = datetime.fromisoformat(daily_raw['sunset'][0])

    # Visibility: Open-Meteo returns meters, convert to miles
    visibility_mi = current_raw['visibility'] / 1609.34

    return {
        'current': {
            'temperature': current_raw['temperature_2m'],
            'feels_like': current_raw['apparent_temperature'],
            'humidity': current_raw['relative_humidity_2m'],
            'wind_speed': current_raw['wind_speed_10m'],
            'weather_code': current_raw['weather_code'],
            'is_day': current_raw['is_day'],
            'uv_index': current_raw['uv_index'],
            'visibility_mi': visibility_mi,
            'dew_point': current_raw['dew_point_2m'],
        },
        'today': {
            'high': daily_raw['temperature_2m_max'][0],
            'low': daily_raw['temperature_2m_min'][0],
            'precip_pct': daily_raw['precipitation_probability_max'][0],
            'sunrise': sunrise_dt.strftime('%I:%M %p').lstrip('0'),  # "6:12 AM"
            'sunset': sunset_dt.strftime('%I:%M %p').lstrip('0'),    # "7:48 PM"
        },
        'hourly': hourly,
        'daily': daily,
    }
```

- [ ] **Step 4: Run the tests — fix the day-of-week assertion if needed**

```bash
python -m pytest tests/test_weather_display.py -v
```

Expected: All 4 tests PASS. If `test_parse_weather_daily_slice` fails on the day name, check what `datetime(2024, 4, 27).strftime('%a')` returns and update the assert to match.

- [ ] **Step 5: Commit**

```bash
git add weather_display.py tests/test_weather_display.py
git commit -m "feat: add parse_weather with hourly slice and daily forecast parsing"
```

---

## Task 3: Icon Mapping and Condition Descriptions (TDD)

**Files:**
- Modify: `weather_display.py` (add WMO mappings + two functions)
- Modify: `tests/test_weather_display.py` (add tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_weather_display.py`:

```python
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
    assert path is not None   # falls back to 02d.png (partly cloudy)


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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_weather_display.py -v -k "icon or wmo or uv_label"
```

Expected: `ImportError` or `AttributeError` on missing functions.

- [ ] **Step 3: Add mappings and functions to weather_display.py**

Add after the `parse_weather` function:

```python
# ---------------------------------------------------------------------------
# WMO weather code mappings
# ---------------------------------------------------------------------------

WMO_TO_OWM = {
    0: '01', 1: '02', 2: '02', 3: '04',
    45: '50', 48: '50',
    51: '09', 53: '09', 55: '09', 56: '09', 57: '09',
    61: '10', 63: '10', 65: '10', 66: '10', 67: '10',
    71: '13', 73: '13', 75: '13', 77: '13',
    80: '09', 81: '09', 82: '09',
    85: '13', 86: '13',
    95: '11', 96: '11', 99: '11',
}

WMO_DESCRIPTIONS = {
    0: 'Clear Sky', 1: 'Mainly Clear', 2: 'Partly Cloudy', 3: 'Overcast',
    45: 'Foggy', 48: 'Icy Fog',
    51: 'Light Drizzle', 53: 'Drizzle', 55: 'Heavy Drizzle',
    56: 'Freezing Drizzle', 57: 'Heavy Freezing Drizzle',
    61: 'Light Rain', 63: 'Rain', 65: 'Heavy Rain',
    66: 'Freezing Rain', 67: 'Heavy Freezing Rain',
    71: 'Light Snow', 73: 'Snow', 75: 'Heavy Snow', 77: 'Snow Grains',
    80: 'Light Showers', 81: 'Showers', 82: 'Heavy Showers',
    85: 'Snow Showers', 86: 'Heavy Snow Showers',
    95: 'Thunderstorm', 96: 'Thunderstorm w/ Hail', 99: 'Severe Thunderstorm',
}


def get_icon_path(wmo_code, is_day, icon_dir):
    """Return path to the OWM icon PNG for a WMO weather code."""
    base = WMO_TO_OWM.get(wmo_code, '02')
    suffix = 'd' if is_day else 'n'
    path = os.path.join(icon_dir, f'{base}{suffix}.png')
    if os.path.exists(path):
        return path
    # Fall back to day variant
    fallback = os.path.join(icon_dir, f'{base}d.png')
    return fallback if os.path.exists(fallback) else None


def wmo_description(code):
    return WMO_DESCRIPTIONS.get(code, 'Unknown')


def uv_label(uv):
    if uv < 3:
        return 'Low'
    if uv < 6:
        return 'Mod'
    if uv < 8:
        return 'High'
    if uv < 11:
        return 'V.High'
    return 'Extreme'
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_weather_display.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add weather_display.py tests/test_weather_display.py
git commit -m "feat: add WMO icon mapping, descriptions, and UV label"
```

---

## Task 4: Fingerprint (TDD)

**Files:**
- Modify: `weather_display.py` (add compute_fingerprint)
- Modify: `tests/test_weather_display.py` (add tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_weather_display.py`:

```python
def test_fingerprint_is_stable():
    from weather_display import parse_weather, compute_fingerprint
    now = datetime(2024, 4, 27, 14, 30)
    weather = parse_weather(SAMPLE_RESPONSE, now=now)
    assert compute_fingerprint(weather) == compute_fingerprint(weather)


def test_fingerprint_changes_on_temp_change():
    from weather_display import parse_weather, compute_fingerprint
    import copy
    now = datetime(2024, 4, 27, 14, 30)
    weather_a = parse_weather(SAMPLE_RESPONSE, now=now)

    modified = copy.deepcopy(SAMPLE_RESPONSE)
    modified['current']['temperature_2m'] = 85.0
    weather_b = parse_weather(modified, now=now)

    assert compute_fingerprint(weather_a) != compute_fingerprint(weather_b)


def test_fingerprint_changes_on_code_change():
    from weather_display import parse_weather, compute_fingerprint
    import copy
    now = datetime(2024, 4, 27, 14, 30)
    weather_a = parse_weather(SAMPLE_RESPONSE, now=now)

    modified = copy.deepcopy(SAMPLE_RESPONSE)
    modified['current']['weather_code'] = 61  # rain
    weather_b = parse_weather(modified, now=now)

    assert compute_fingerprint(weather_a) != compute_fingerprint(weather_b)
```

- [ ] **Step 2: Run to confirm they fail**

```bash
python -m pytest tests/test_weather_display.py -v -k "fingerprint"
```

Expected: `AttributeError: module 'weather_display' has no attribute 'compute_fingerprint'`

- [ ] **Step 3: Add compute_fingerprint to weather_display.py**

Add after `uv_label`:

```python
# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def compute_fingerprint(weather):
    """Hash key weather fields to detect meaningful changes."""
    parts = [
        str(round(weather['current']['temperature'])),
        str(weather['current']['weather_code']),
    ] + [str(round(h['temp'])) for h in weather['hourly']]
    return hashlib.md5(','.join(parts).encode()).hexdigest()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_weather_display.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add weather_display.py tests/test_weather_display.py
git commit -m "feat: add compute_fingerprint for change detection"
```

---

## Task 5: Weather Fetching (TDD)

**Files:**
- Modify: `weather_display.py` (add fetch_weather + BASE_URL)
- Modify: `tests/test_weather_display.py` (add tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_weather_display.py`:

```python
def test_fetch_weather_calls_correct_url(monkeypatch):
    from weather_display import fetch_weather
    import requests as req

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
    from weather_display import fetch_weather
    import requests as req

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
```

- [ ] **Step 2: Run to confirm they fail**

```bash
python -m pytest tests/test_weather_display.py -v -k "fetch"
```

Expected: `AttributeError: module 'weather_display' has no attribute 'fetch_weather'`

- [ ] **Step 3: Add fetch_weather to weather_display.py**

Add after `compute_fingerprint`:

```python
# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

BASE_URL = 'https://api.open-meteo.com/v1/forecast'


def fetch_weather():
    """Fetch current, hourly, and daily weather from Open-Meteo."""
    params = {
        'latitude': config.LATITUDE,
        'longitude': config.LONGITUDE,
        'current': (
            'temperature_2m,apparent_temperature,relative_humidity_2m,'
            'wind_speed_10m,weather_code,is_day,uv_index,visibility,dew_point_2m'
        ),
        'hourly': 'temperature_2m,weather_code,precipitation_probability,wind_speed_10m',
        'daily': (
            'temperature_2m_max,temperature_2m_min,weather_code,'
            'precipitation_probability_max,sunrise,sunset'
        ),
        'temperature_unit': 'fahrenheit',
        'wind_speed_unit': 'mph',
        'precipitation_unit': 'inch',
        'timezone': 'America/New_York',
        'forecast_days': 7,
    }
    resp = requests.get(BASE_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_weather_display.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add weather_display.py tests/test_weather_display.py
git commit -m "feat: add fetch_weather using Open-Meteo API"
```

---

## Task 6: Render Function (TDD)

**Files:**
- Modify: `weather_display.py` (add render + helper functions + font/path constants)
- Modify: `tests/test_weather_display.py` (add test)

The render function produces a 1-bit PIL Image at 800×480. It calls three private sub-functions for the left panel, hourly panel, and daily panel.

- [ ] **Step 1: Add failing render test**

Append to `tests/test_weather_display.py`:

```python
def test_render_returns_correct_image():
    from weather_display import parse_weather, render
    from PIL import Image as PILImage
    base_dir = os.path.dirname(os.path.dirname(__file__))
    picdir = os.path.join(base_dir, 'images')
    icondir = os.path.join(picdir, 'icon')
    fontdir = os.path.join(base_dir, 'font')

    now = datetime(2024, 4, 27, 14, 30)
    weather = parse_weather(SAMPLE_RESPONSE, now=now)
    result = render(weather, picdir, icondir, fontdir)

    assert isinstance(result, PILImage.Image)
    assert result.size == (800, 480)
    assert result.mode == '1'
```

- [ ] **Step 2: Run to confirm it fails**

```bash
python -m pytest tests/test_weather_display.py -v -k "render"
```

Expected: `AttributeError: module 'weather_display' has no attribute 'render'`

- [ ] **Step 3: Add directory constants and font loader to weather_display.py**

Add near the top of `weather_display.py`, after the imports:

```python
BASE_DIR = os.path.dirname(os.path.realpath(__file__))
PICDIR = os.path.join(BASE_DIR, 'images')
ICONDIR = os.path.join(PICDIR, 'icon')
FONTDIR = os.path.join(BASE_DIR, 'font')
```

- [ ] **Step 4: Add render helpers and render() to weather_display.py**

Add after `fetch_weather`:

```python
# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

BLACK = 0
WHITE = 255


def _load_fonts(fontdir):
    path = os.path.join(fontdir, 'Font.ttc')
    return {
        15: ImageFont.truetype(path, 15),
        20: ImageFont.truetype(path, 20),
        22: ImageFont.truetype(path, 22),
        35: ImageFont.truetype(path, 35),
        60: ImageFont.truetype(path, 60),
    }


def _center_text(draw, cx, y, text, font):
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0]
    draw.text((cx - w // 2, y), text, font=font, fill=BLACK)


def _paste_icon(img, icon_path, cx, y, size):
    """Paste a weather icon centered at cx, top-left at y."""
    if icon_path is None:
        return
    icon = Image.open(icon_path).resize((size, size)).convert('1')
    img.paste(icon, (cx - size // 2, y))


def _draw_left_panel(draw, img, weather, icondir, fonts):
    c = weather['current']
    t = weather['today']
    now = datetime.now()

    x_label = 12
    x_value = 175

    # Location + date header
    draw.text((x_label, 8), config.LOCATION, font=fonts[22], fill=BLACK)
    date_str = now.strftime('%a %b %d  %I:%M %p').replace(' 0', ' ')
    draw.text((x_label, 36), date_str, font=fonts[15], fill=BLACK)

    # Condition description
    desc = wmo_description(c['weather_code'])
    draw.text((x_label, 57), desc, font=fonts[15], fill=BLACK)

    # Icon (100×100) at left, temperature alongside
    icon_path = get_icon_path(c['weather_code'], c['is_day'], icondir)
    _paste_icon(img, icon_path, cx=60, y=76, size=100)

    temp_str = f'{round(c["temperature"])}°F'
    draw.text((130, 85), temp_str, font=fonts[60], fill=BLACK)

    # Details grid
    pairs = [
        ('Feels like', f'{round(c["feels_like"])}°F'),
        ('Wind',       f'{round(c["wind_speed"])} mph'),
        ('Humidity',   f'{c["humidity"]}%'),
        ('High / Low', f'{round(t["high"])}° / {round(t["low"])}°'),
        ('Precip',     f'{t["precip_pct"]}%'),
    ]
    y = 185
    for label, value in pairs:
        draw.text((x_label, y), label, font=fonts[15], fill=BLACK)
        draw.text((x_value, y), value, font=fonts[15], fill=BLACK)
        y += 21


def _draw_hourly_panel(draw, img, weather, icondir, fonts):
    # Column centers: 337 + i*61 for i=0..7
    draw.text((315, 8), 'NEXT 8 HOURS', font=fonts[15], fill=BLACK)

    for i, h in enumerate(weather['hourly']):
        cx = 337 + i * 61
        _center_text(draw, cx, 28, h['time'], fonts[15])
        icon_path = get_icon_path(h['weather_code'], is_day=1, icon_dir=icondir)
        _paste_icon(img, icon_path, cx=cx, y=48, size=40)
        _center_text(draw, cx, 93, f'{round(h["temp"])}°', fonts[20])
        _center_text(draw, cx, 115, f'{h["precip_pct"]}%', fonts[15])
        _center_text(draw, cx, 135, f'{round(h["wind_speed"])}mph', fonts[15])

    # Divider between hourly and stats
    draw.line([(307, 157), (799, 157)], fill=BLACK, width=1)


def _draw_stats_bar(draw, weather, fonts):
    c = weather['current']
    t = weather['today']

    uv_str = f'UV {round(c["uv_index"])} {uv_label(c["uv_index"])}'
    vis_str = f'Vis {round(c["visibility_mi"])}mi'
    dew_str = f'Dew {round(c["dew_point"])}°F'
    rise_str = f'↑{t["sunrise"]}'
    set_str = f'↓{t["sunset"]}'

    items = [uv_str, vis_str, dew_str, rise_str, set_str]
    # 5 items across right panel (x=307 to 799, width=493)
    # centers: 307 + 49 + i*99
    for i, text in enumerate(items):
        cx = 356 + i * 99
        _center_text(draw, cx, 172, text, fonts[15])


def _draw_daily_panel(draw, img, weather, icondir, fonts):
    draw.text((12, 298), '7-DAY FORECAST', font=fonts[15], fill=BLACK)

    for i, d in enumerate(weather['daily']):
        cx = 57 + i * 114

        # Day name — underline today
        day_str = d['day']
        bbox = fonts[15].getbbox(day_str)
        w = bbox[2] - bbox[0]
        x = cx - w // 2
        draw.text((x, 318), day_str, font=fonts[15], fill=BLACK)
        if d['is_today']:
            draw.line([(x, 336), (x + w, 336)], fill=BLACK, width=1)

        icon_path = get_icon_path(d['weather_code'], is_day=1, icon_dir=icondir)
        _paste_icon(img, icon_path, cx=cx, y=340, size=50)

        _center_text(draw, cx, 394, f'{round(d["high"])}°', fonts[20])
        _center_text(draw, cx, 416, f'{round(d["low"])}°', fonts[15])
        _center_text(draw, cx, 436, f'{d["precip_pct"]}%', fonts[15])


# ---------------------------------------------------------------------------
# Main render entry point
# ---------------------------------------------------------------------------

def render(weather, picdir, icondir, fontdir):
    """Render weather data to an 800×480 1-bit PIL Image."""
    img = Image.new('1', (800, 480), WHITE)
    draw = ImageDraw.Draw(img)
    fonts = _load_fonts(fontdir)

    # Structural dividers
    draw.line([(305, 0), (305, 293)], fill=BLACK, width=2)   # vertical
    draw.line([(0, 293), (800, 293)], fill=BLACK, width=2)   # horizontal main

    _draw_left_panel(draw, img, weather, icondir, fonts)
    _draw_hourly_panel(draw, img, weather, icondir, fonts)
    _draw_stats_bar(draw, weather, fonts)
    _draw_daily_panel(draw, img, weather, icondir, fonts)

    return img
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_weather_display.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Spot-check rendering locally (dev mode)**

```bash
python -c "
from weather_display import render
from PIL import Image
import datetime

# Build minimal weather dict for quick visual check
from tests.test_weather_display import SAMPLE_RESPONSE, _make_api_response
from weather_display import parse_weather
w = parse_weather(SAMPLE_RESPONSE, now=datetime.datetime(2024,4,27,14,30))
img = render(w, 'images', 'images/icon', 'font')
img.save('images/screen_output.png')
print('Saved to images/screen_output.png — open to inspect')
"
```

Open `images/screen_output.png` to visually verify layout. Adjust pixel positions in `_draw_left_panel`, `_draw_hourly_panel`, or `_draw_daily_panel` as needed — re-run until the output looks correct.

- [ ] **Step 7: Commit**

```bash
git add weather_display.py tests/test_weather_display.py
git commit -m "feat: add render function with left/hourly/stats/daily panels"
```

---

## Task 7: Write to Display (TDD)

**Files:**
- Modify: `weather_display.py` (add write_to_display)
- Modify: `tests/test_weather_display.py` (add test)

- [ ] **Step 1: Add failing test**

Append to `tests/test_weather_display.py`:

```python
def test_write_to_display_dev_mode_saves_file(tmp_path):
    from weather_display import write_to_display
    from PIL import Image as PILImage
    img = PILImage.new('1', (800, 480), 255)
    write_to_display(img, epd=None, picdir=str(tmp_path))
    assert (tmp_path / 'screen_output.png').exists()
```

- [ ] **Step 2: Run to confirm it fails**

```bash
python -m pytest tests/test_weather_display.py -v -k "write_to_display"
```

Expected: `AttributeError: module 'weather_display' has no attribute 'write_to_display'`

- [ ] **Step 3: Add write_to_display to weather_display.py**

Add after the `render` function:

```python
# ---------------------------------------------------------------------------
# Display output
# ---------------------------------------------------------------------------

def write_to_display(image, epd=None, picdir=None):
    """Write image to e-ink display, or save PNG in dev mode if epd is None."""
    if epd is None:
        path = os.path.join(picdir or PICDIR, 'screen_output.png')
        image.save(path)
        logging.info(f'Dev mode: saved to {path}')
        return
    epd.init()
    epd.display(epd.getbuffer(image))
    epd.sleep()
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_weather_display.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add weather_display.py tests/test_weather_display.py
git commit -m "feat: add write_to_display with e-ink and dev-mode PNG fallback"
```

---

## Task 8: Main Loop

**Files:**
- Modify: `weather_display.py` (add main function)

No unit test for the loop itself — verified by running on the Pi in Task 9.

- [ ] **Step 1: Add main() to the bottom of weather_display.py**

```python
# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    logging.info('WeatherDisplay starting.')

    # Initialize e-ink display once at startup
    epd = None
    if EPD_AVAILABLE:
        epd = epd7in5_V2.EPD()
        epd.init()
        epd.Clear()
        logging.info('E-ink display initialized and cleared.')
    else:
        logging.info('No e-ink module — running in dev mode (saves PNG).')

    last_fingerprint = None
    retry_delay = 1800  # 30 minutes

    while True:
        try:
            raw = fetch_weather()
            weather = parse_weather(raw)
            fingerprint = compute_fingerprint(weather)

            if fingerprint != last_fingerprint:
                logging.info('Weather changed — updating display.')
                image = render(weather, PICDIR, ICONDIR, FONTDIR)
                write_to_display(image, epd=epd, picdir=PICDIR)
                last_fingerprint = fingerprint
            else:
                logging.info('No weather change — display unchanged.')

            retry_delay = 1800  # reset to 30 min on success

        except requests.RequestException as exc:
            logging.error(f'API error: {exc} — retrying in 5 minutes.')
            retry_delay = 300

        except Exception as exc:
            logging.error(f'Unexpected error: {exc} — retrying in 5 minutes.')
            retry_delay = 300

        time.sleep(retry_delay)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run all tests one final time**

```bash
python -m pytest tests/test_weather_display.py -v
```

Expected: All tests PASS.

- [ ] **Step 3: Do a local dev-mode smoke test**

```bash
python weather_display.py
```

Expected output (no Pi attached):
```
2026-04-27 HH:MM:SS WeatherDisplay starting.
2026-04-27 HH:MM:SS No e-ink module — running in dev mode (saves PNG).
2026-04-27 HH:MM:SS Weather changed — updating display.
2026-04-27 HH:MM:SS Dev mode: saved to .../images/screen_output.png
```

Open `images/screen_output.png` to visually verify the full layout looks correct.

- [ ] **Step 4: Commit**

```bash
git add weather_display.py
git commit -m "feat: add main loop with 30-min polling and change-only refresh"
```

---

## Task 9: Deploy and Test on Pi

**Files:** No new files — deploy via git pull.

- [ ] **Step 1: Push to remote**

```bash
git push origin main
```

- [ ] **Step 2: SSH into the Pi and pull**

```bash
ssh pi@192.168.1.162   # password: raspberry
cd ~/TideTracker       # or wherever the repo lives; if not cloned yet: git clone <repo-url>
git pull origin main
```

- [ ] **Step 3: Install dependencies if needed**

```bash
pip3 install requests Pillow
```

- [ ] **Step 4: Run a single-shot smoke test**

```bash
python3 -c "
from weather_display import fetch_weather, parse_weather, render, write_to_display, PICDIR, ICONDIR, FONTDIR
raw = fetch_weather()
w = parse_weather(raw)
print('Temp:', round(w['current']['temperature']), 'F')
print('Hourly hours:', [h['time'] for h in w['hourly']])
img = render(w, PICDIR, ICONDIR, FONTDIR)
write_to_display(img, epd=None, picdir=PICDIR)
print('Saved screen_output.png')
"
```

Expected: prints current temp, 8 hour labels, saves PNG to `images/screen_output.png`. Copy the PNG back with `scp` to inspect it visually:

```bash
# Run from Mac:
scp pi@192.168.1.162:~/TideTracker/images/screen_output.png /tmp/pi_screen.png
open /tmp/pi_screen.png
```

- [ ] **Step 5: Run with the real display**

```bash
python3 weather_display.py
```

Expected: e-ink display initializes, clears, then shows the weather layout. Subsequent polls every 30 minutes only refresh when weather changes.

- [ ] **Step 6: (Optional) Set up as a systemd service so it runs on boot**

```bash
sudo nano /etc/systemd/system/weather.service
```

Paste:
```ini
[Unit]
Description=WeatherDisplay
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/TideTracker/weather_display.py
WorkingDirectory=/home/pi/TideTracker
Restart=on-failure
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable weather.service
sudo systemctl start weather.service
sudo systemctl status weather.service
```

Expected: `Active: active (running)`

---

## Self-Review Checklist

- [x] **config.py** stripped to location constants — Task 1
- [x] **Open-Meteo API** single request, all required fields — Task 5
- [x] **parse_weather** hourly slice from current hour, 7-day daily, visibility m→mi, sunrise/sunset formatting — Task 2
- [x] **WMO → OWM icon mapping** all code ranges covered, fallback for unknown — Task 3
- [x] **wmo_description** all codes mapped — Task 3
- [x] **uv_label** 5 levels — Task 3
- [x] **compute_fingerprint** hashes temp + code + hourly temps — Task 4
- [x] **render** 800×480 '1'-mode image, all 3 panels + stats bar — Task 6
- [x] **Layout B**: left current / right hourly+stats / bottom 7-day — Task 6
- [x] **8 hourly columns** each with time/icon/temp/precip/wind — Task 6
- [x] **Stats bar**: UV, visibility, dew point, sunrise, sunset — Task 6
- [x] **Today underlined** in daily row — Task 6
- [x] **write_to_display** e-ink path + dev-mode PNG fallback — Task 7
- [x] **main loop** 30-min poll, change-only refresh, 5-min retry on error — Task 8
- [x] **Pi deploy + systemd** — Task 9
- [x] **No forced periodic refresh** — display only updates on fingerprint change — Task 8
- [x] **On startup always renders** (last_fingerprint starts None) — Task 8
