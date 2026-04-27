import os
import sys
import time
import hashlib
import logging
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

EPD_AVAILABLE = False
try:
    from lib.waveshare_epd import epd7in5_V2
    EPD_AVAILABLE = True
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
PICDIR = os.path.join(BASE_DIR, 'images')
ICONDIR = os.path.join(PICDIR, 'icon')
FONTDIR = os.path.join(BASE_DIR, 'font')


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

    # Find the index of the current hour in the hourly array
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
            'time': t.strftime('%I %p').lstrip('0'),
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
            'sunrise': sunrise_dt.strftime('%I:%M %p').lstrip('0'),
            'sunset': sunset_dt.strftime('%I:%M %p').lstrip('0'),
        },
        'hourly': hourly,
        'daily': daily,
    }
