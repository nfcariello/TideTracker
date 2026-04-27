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

    # Use API current.time (already in API timezone) to find the hour index.
    # This avoids the Pi's system clock/timezone affecting forecast alignment.
    try:
        hour_idx = hourly_raw['time'].index(current_raw['time'])
    except ValueError:
        # Fall back to the now-based lookup if the API time isn't an exact match
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
    # Use the API's current.time (already in local/Eastern timezone) for display
    display_time = datetime.fromisoformat(current_raw['time'])

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
        'display_time': display_time,
        'hourly': hourly,
        'daily': daily,
    }


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
    """Return absolute path to the OWM icon PNG for a WMO code, or None."""
    base = WMO_TO_OWM.get(wmo_code, '02')
    suffix = 'd' if is_day else 'n'
    path = os.path.join(icon_dir, f'{base}{suffix}.png')
    if os.path.exists(path):
        return path
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


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

BLACK = 0
WHITE = 255


def _load_fonts(fontdir):
    path = os.path.join(fontdir, 'Font.ttc')
    return {
        15: ImageFont.truetype(path, 15),
        18: ImageFont.truetype(path, 18),
        20: ImageFont.truetype(path, 20),
        22: ImageFont.truetype(path, 22),
        24: ImageFont.truetype(path, 24),
        40: ImageFont.truetype(path, 40),
        60: ImageFont.truetype(path, 60),
    }


def _center_text(draw, cx, y, text, font):
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0]
    draw.text((cx - w // 2, y), text, font=font, fill=BLACK)


def _paste_icon(img, icon_path, cx, y, size):
    """Paste an icon (size×size) centered horizontally at cx, top at y."""
    if icon_path is None:
        return
    icon = Image.open(icon_path).resize((size, size)).convert('1')
    img.paste(icon, (cx - size // 2, y))


def _draw_left_panel(draw, img, weather, icondir, fonts):
    c = weather['current']
    t = weather['today']
    dt = weather['display_time']  # Eastern time from API

    x_label = 12
    x_value = 145

    # Header line 1: location (large) + date (right-aligned, small)
    draw.text((x_label, 8), config.LOCATION, font=fonts[22], fill=BLACK)
    date_str = dt.strftime('%a, %b %d').replace(' 0', ' ')
    bbox = fonts[15].getbbox(date_str)
    draw.text((300 - (bbox[2] - bbox[0]) - 6, 16), date_str, font=fonts[15], fill=BLACK)

    # Header line 2: condition (left) + time (right-aligned)
    desc = wmo_description(c['weather_code'])
    draw.text((x_label, 38), desc, font=fonts[15], fill=BLACK)
    time_str = dt.strftime('%I:%M %p').lstrip('0')
    bbox = fonts[15].getbbox(time_str)
    draw.text((300 - (bbox[2] - bbox[0]) - 6, 38), time_str, font=fonts[15], fill=BLACK)

    # Icon + big temperature
    icon_path = get_icon_path(c['weather_code'], c['is_day'], icondir)
    _paste_icon(img, icon_path, cx=58, y=60, size=85)
    draw.text((125, 65), f'{round(c["temperature"])}°F', font=fonts[60], fill=BLACK)

    # Details — font18, 22px line height, sun row combined.
    # Sun times drop AM/PM to fit; arrows make morning/evening obvious.
    sunrise_short = t['sunrise'].rsplit(' ', 1)[0]   # "6:12 AM" -> "6:12"
    sunset_short  = t['sunset'].rsplit(' ', 1)[0]
    pairs = [
        ('Feels like', f'{round(c["feels_like"])}°F'),
        ('Wind',       f'{round(c["wind_speed"])} mph'),
        ('Humidity',   f'{c["humidity"]}%'),
        ('High / Low', f'{round(t["high"])}° / {round(t["low"])}°'),
        ('Precip',     f'{t["precip_pct"]}%'),
        ('Sun',        f'↑ {sunrise_short}   ↓ {sunset_short}'),
    ]
    y = 158
    for label, value in pairs:
        draw.text((x_label, y), label, font=fonts[18], fill=BLACK)
        draw.text((x_value, y), value, font=fonts[18], fill=BLACK)
        y += 22


def _draw_hourly_panel(draw, img, weather, icondir, fonts):
    """Right panel — 6 hourly columns, full available height."""
    draw.text((315, 8), 'NEXT 6 HOURS', font=fonts[15], fill=BLACK)

    # 6 columns across 493px wide right panel = ~82px each
    # cx = 307 + 41 + i*82 -> 348, 430, 512, 594, 676, 758
    hours = weather['hourly'][:6]
    for i, h in enumerate(hours):
        cx = 348 + i * 82

        # Time label (font22)
        _center_text(draw, cx, 32, h['time'], fonts[22])

        # Icon (75×75)
        icon_path = get_icon_path(h['weather_code'], is_day=h.get('is_day', 1), icon_dir=icondir)
        _paste_icon(img, icon_path, cx=cx, y=62, size=75)

        # Temperature (font40 — the dominant hourly datum)
        _center_text(draw, cx, 148, f'{round(h["temp"])}°', fonts[40])

        # Precipitation %
        _center_text(draw, cx, 213, f'{h["precip_pct"]}%', fonts[22])

        # Wind speed
        _center_text(draw, cx, 245, f'{round(h["wind_speed"])} mph', fonts[18])



def _draw_daily_panel(draw, img, weather, icondir, fonts):
    draw.text((12, 298), '7-DAY FORECAST', font=fonts[15], fill=BLACK)

    for i, d in enumerate(weather['daily']):
        cx = 57 + i * 114

        # Day name (font20), underline today
        day_str = d['day']
        bbox = fonts[20].getbbox(day_str)
        w = bbox[2] - bbox[0]
        x = cx - w // 2
        draw.text((x, 316), day_str, font=fonts[20], fill=BLACK)
        if d['is_today']:
            draw.line([(x, 339), (x + w, 339)], fill=BLACK, width=1)

        # Icon (60×60)
        icon_path = get_icon_path(d['weather_code'], is_day=1, icon_dir=icondir)
        _paste_icon(img, icon_path, cx=cx, y=343, size=60)

        # Temps and precip — tightened vertical spacing so precip fits in 480
        _center_text(draw, cx, 408, f'{round(d["high"])}°', fonts[24])
        _center_text(draw, cx, 437, f'{round(d["low"])}°',  fonts[18])
        _center_text(draw, cx, 459, f'{d["precip_pct"]}%',  fonts[15])


def render(weather, picdir, icondir, fontdir):
    """Render weather data to an 800×480 1-bit PIL Image."""
    img = Image.new('1', (800, 480), WHITE)
    draw = ImageDraw.Draw(img)
    fonts = _load_fonts(fontdir)

    # Structural dividers
    draw.line([(305, 0),   (305, 293)], fill=BLACK, width=2)  # vertical
    draw.line([(0,   293), (800, 293)], fill=BLACK, width=2)  # horizontal main

    _draw_left_panel(draw, img, weather, icondir, fonts)
    _draw_hourly_panel(draw, img, weather, icondir, fonts)
    _draw_daily_panel(draw, img, weather, icondir, fonts)

    return img


# ---------------------------------------------------------------------------
# Display output
# ---------------------------------------------------------------------------

def write_to_display(image, epd=None, picdir=None):
    """Write image to e-ink, or save PNG in dev mode when epd is None."""
    if epd is None:
        path = os.path.join(picdir or PICDIR, 'screen_output.png')
        image.save(path)
        logging.info(f'Dev mode: saved to {path}')
        return
    epd.init()
    epd.display(epd.getbuffer(image))
    epd.sleep()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    logging.info('WeatherDisplay starting.')

    epd = None
    if EPD_AVAILABLE:
        epd = epd7in5_V2.EPD()
        epd.init()
        epd.Clear()
        logging.info('E-ink display initialized and cleared.')
    else:
        logging.info('No e-ink module — running in dev mode (saves PNG).')

    last_fingerprint = None
    retry_delay = 1800

    while True:
        try:
            raw = fetch_weather()
            weather = parse_weather(raw)
            fingerprint = compute_fingerprint(weather)

            changed = fingerprint != last_fingerprint
            logging.info('Refreshing display (weather %s).',
                         'changed' if changed else 'unchanged')
            image = render(weather, PICDIR, ICONDIR, FONTDIR)
            write_to_display(image, epd=epd, picdir=PICDIR)
            last_fingerprint = fingerprint

            retry_delay = 1800

        except requests.RequestException as exc:
            logging.error(f'API error: {exc} — retrying in 5 minutes.')
            retry_delay = 300

        except Exception as exc:
            logging.error(f'Unexpected error: {exc} — retrying in 5 minutes.')
            retry_delay = 300

        time.sleep(retry_delay)


if __name__ == '__main__':
    main()
