# WeatherDisplay — E-Ink Design Spec

**Date:** 2026-04-27  
**Target hardware:** Raspberry Pi Zero W + Waveshare 7.5" V2 e-ink display (800×480, black & white)

---

## Overview

Replace the existing `TideTracker.py` (tide + owlet + weather) with a focused weather-only display. A single script polls Open-Meteo every 30 minutes, compares a data fingerprint to detect changes, and redraws the e-ink screen only when the weather actually changes. The display is static by design — no unnecessary refreshes.

---

## Files

| File | Role |
|---|---|
| `weather_display.py` | Single main script — fetch, compare, render, write to e-ink |
| `config.py` | Location constants only (lat, lon, location name) |
| `owlet_monitor.py` | Left on disk, never imported |
| `lib/waveshare_epd/` | Unchanged e-ink driver |
| `images/icon/` | Existing OWM icon PNGs, reused as-is |
| `font/Font.ttc` | Existing font, reused as-is |

---

## Configuration (`config.py`)

```python
LOCATION = 'Wantagh, NY'
LATITUDE = 40.6734
LONGITUDE = -73.5132
```

No API key required — Open-Meteo is free and unauthenticated.

---

## Weather Data

**API:** `https://api.open-meteo.com/v1/forecast`

**Single request per poll** returning:
- `current`: temperature_2m, apparent_temperature, relative_humidity_2m, wind_speed_10m, weather_code, is_day, uv_index, visibility, dew_point_2m. Precip % for "today" comes from `daily[0].precipitation_probability_max` (Open-Meteo does not expose precipitation_probability in the current block)
- `hourly`: temperature_2m, weather_code, precipitation_probability, wind_speed_10m (next 8 hours, starting from the current hour rounded down — e.g. at 2:45 PM, start at index for 2 PM)
- `daily`: temperature_2m_max, temperature_2m_min, weather_code, precipitation_probability_max, sunrise, sunset (7 days)

**Units:** Imperial (temperature_unit=fahrenheit, wind_speed_unit=mph, precipitation_unit=inch)

---

## Update Logic

```
loop every 30 minutes:
    data = fetch_weather()
    fingerprint = hash(current_temp, current_code, hourly_temps[0:8])
    if fingerprint != last_fingerprint:
        image = render(data)
        write_to_eink(image)
        last_fingerprint = fingerprint
    sleep(1800)
```

- **No forced periodic refresh** — screen only updates when data changes
- On API failure: log error, keep existing image on screen, retry after 5 minutes
- On startup: always render and write regardless of fingerprint

---

## Display Layout (800×480)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ LEFT PANEL (304px)       │ TOP-RIGHT PANEL (496px)                      │
│                          │                                               │
│ Wantagh, NY              │ NEXT 8 HOURS                                  │
│ Mon Apr 27 · 2:00 PM     │  2PM   3PM   4PM   5PM   6PM   7PM   8PM   9PM │
│                          │  ☀     ⛅    ⛅    ☁    🌧   🌧   ⛅   ☁    │
│ [ICON]  72°F             │  74°   73°   71°   69°   66°   64°   63°  62° │
│ Partly Cloudy            │  5%    10%   15%   20%   75%   80%   30%  15% │
│                          │  6mph  7mph  9mph 11mph 14mph 13mph 10mph 8mph │
│ Feels like   68°F        ├───────────────────────────────────────────────┤
│ Wind         8 mph       │ UV: 3 Mod  Vis: 10mi  Dew: 56°  ↑6:12  ↓7:48 │
│ Humidity     62%         │                                               │
│ High / Low   76° / 58°   │                                               │
│ Precip       10%         │                                               │
├──────────────────────────┴───────────────────────────────────────────────┤
│ 7-DAY FORECAST                                                            │
│  Mon    Tue    Wed    Thu    Fri    Sat    Sun                            │
│  ☀      ⛅    🌧    ⛅    ☀    ☀    ⛅                               │
│  76°    70°   65°   68°   73°   78°   72°                               │
│  58°    55°   52°   54°   56°   60°   58°                               │
│  5%     20%   80%   30%   5%    0%    15%                               │
└───────────────────────────────────────────────────────────────────────────┘
```

**Left panel (x: 0–304, y: 0–~290):**
- Location name + date/time (small, top)
- Weather icon (100×100px, from `images/icon/`)
- Current temperature (large font ~60pt)
- Condition label (~22pt)
- Details grid: feels like / wind / humidity / high-low / precip (monospaced ~20pt)

**Top-right panel (x: 307–800, y: 0–~290):**
- 8 columns, one per hour starting from current hour
- Each column: time label / icon (50×50px) / temp / precip % / wind speed
- Stats bar at bottom of panel: UV index, visibility, dew point, sunrise time, sunset time

**Bottom panel (x: 0–800, y: ~293–480):**
- Horizontal dividing line at y≈293
- 7 columns, one per day starting today
- Each column: day name (today underlined) / icon (50×50px) / high temp / low temp / precip %

**Dividing lines:**
- Vertical line at x=305, y=0 to y=293 (separates left from right panels)
- Horizontal line at y=293, x=0 to x=800 (separates top from weekly)
- Horizontal line within right panel below the 8 hourly columns, above the stats bar

---

## Icon Mapping

Existing OWM icon PNGs (`images/icon/`) are reused. Open-Meteo returns WMO weather codes, mapped as follows:

| WMO codes | OWM icon | Condition |
|---|---|---|
| 0 | 01d / 01n | Clear sky |
| 1, 2 | 02d / 02n | Mainly clear / partly cloudy |
| 3 | 04d / 04n | Overcast |
| 45, 48 | 50d / 50n | Fog |
| 51, 53, 55, 56, 57 | 09d / 09n | Drizzle |
| 61, 63, 65, 66, 67 | 10d / 10n | Rain |
| 71, 73, 75, 77 | 13d / 13n | Snow |
| 80, 81, 82 | 09d / 09n | Rain showers |
| 85, 86 | 13d / 13n | Snow showers |
| 95, 96, 99 | 11d / 11n | Thunderstorm |

Day/night variant (`d` vs `n`) chosen by comparing current hour against today's sunrise/sunset times from the API response.

---

## E-Ink Driver Usage

```python
epd = epd7in5_V2.EPD()
epd.init()
epd.display(epd.getbuffer(image))
epd.sleep()   # low-power hold between updates
# on next update:
epd.init()    # wake before displaying
```

The display is put to sleep between updates to prevent damage. `epd.init()` is called before each write. `epd.Clear()` is called once at startup only.

---

## Error Handling

- **API failure:** Log to stdout, keep existing screen image, retry after 5 minutes (not 30)
- **Missing icon file:** Fall back to a blank white square of the same size — never crash
- **No EPD module (dev/test mode):** Catch import error, save rendered image to `images/screen_output.png` and continue — allows local testing without hardware

---

## Dependencies

All already installed on the Pi or available via pip:

```
requests
Pillow
```

Open-Meteo requires no SDK — plain `requests.get()` to a public URL.

---

## Out of Scope

- Tide data
- Owlet monitor
- Threading (single-threaded poll loop)
- Any display animation or partial refresh
