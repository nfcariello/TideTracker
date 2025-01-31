'''
****************************************************************
****************************************************************

                TideTracker for E-Ink Display

                        by Sam Baker

****************************************************************
****************************************************************
'''
import glob
import sys
import os
import threading
import time
import traceback
import requests, json
from io import BytesIO
import noaa_coops as nc
import matplotlib.pyplot as plt
import numpy as np
import datetime as dt
import config
import owlet_monitor
import pandas as pd

sys.path.append('lib')
try:
    from lib.waveshare_epd import epd7in5_V2
except:
    print("No EPD module found, falling back to console print")
from PIL import Image, ImageDraw, ImageFont

picdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'images')
icondir = os.path.join(picdir, 'icon')
fontdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'font')

'''
****************************************************************

Location specific info required

****************************************************************
'''
# Start the Owlet Monitor
# owlet_monitor.main()

# Optional, displayed on top left
LOCATION = 'East Rockaway, NY'
# NOAA Station Code for tide data
StationID = 'KWO35'

# For weather data
# Create Account on openweathermap.com and get API key
API_KEY = config.API_KEY
# Get LATITUDE and LONGITUDE of location
LATITUDE = '40.6415296'
LONGITUDE = '-73.6656011'
UNITS = 'imperial'

# Create URL for API call
BASE_URL = 'http://api.openweathermap.org/data/2.5/onecall?'
URL = BASE_URL + 'lat=' + LATITUDE + '&lon=' + LONGITUDE + '&units=' + UNITS +'&appid=' + API_KEY


'''
****************************************************************

Functions and defined variables

****************************************************************
'''

# Time intervals for updates
WEATHER_UPDATE_INTERVAL = 600  # Update weather data every 10 minutes (in seconds)
OWLET_CHECK_INTERVAL = 10  # Check owlet data transmission every 10 seconds (in seconds)


# define funciton for writing image and sleeping for specified time
def write_to_screen(image, sleep_seconds):
    print('Writing to screen.') # for debugging
    # Create new blank image template matching screen resolution
    h_image = Image.new('1', (epd.width, epd.height), 255)
    # Open the template
    screen_output_file = Image.open(os.path.join(picdir, image))
    # Initialize the drawing context with template as background
    h_image.paste(screen_output_file, (0, 0))
    epd.display(epd.getbuffer(h_image))
    # Sleep
    epd.sleep() # Put screen to sleep to prevent damage
    print('Sleeping for ' + str(sleep_seconds) +'.')
    time.sleep(sleep_seconds) # Determines refresh rate on data
    epd.init() # Re-Initialize screen


# define function for displaying error
def display_error(error_source):
    # Display an error
    print('Error in the', error_source, 'request.')
    # Initialize drawing
    error_image = Image.new('1', (epd.width, epd.height), 255)
    # Initialize the drawing
    draw = ImageDraw.Draw(error_image)
    draw.text((100, 150), error_source +' ERROR', font=font50, fill=black)
    draw.text((100, 300), 'Retrying in 30 seconds', font=font22, fill=black)
    current_time = dt.datetime.now().strftime('%H:%M')
    draw.text((300, 365), 'Last Refresh: ' + str(current_time), font = font50, fill=black)
    # Save the error image
    error_image_file = 'error.png'
    error_image.save(os.path.join(picdir, error_image_file))
    # Close error image
    error_image.close()
    # Write error to screen
    write_to_screen(error_image_file, 30)


# define function for getting weather data
def getWeather(URL):
    # Ensure there are no errors with connection
    error_connect = True
    while error_connect == True:
        try:
            # HTTP request
            print('Attempting to connect to OWM.')
            response = requests.get(URL)
            print('Connection to OWM successful.')
            error_connect = None
        except:
            # Call function to display connection error
            print('Connection error.')
            display_error('CONNECTION')

    # Check status of code request
    if response.status_code == 200:
        print('Connection to Open Weather successful.')
        # get data in jason format
        data = response.json()

        with open('data.txt', 'w') as outfile:
            json.dump(data, outfile)

        return data

    else:
        # Call function to display HTTP error
        display_error('HTTP')


# last 24 hour data, add argument for start/end_date
def past24(StationID):
    # Create Station Object
    stationdata = nc.Station(StationID)

    # Get today date string
    today = dt.datetime.now()
    todaystr = today.strftime("%Y%m%d %H:%M")
    # Get yesterday date string
    yesterday = today - dt.timedelta(days=1)
    yesterdaystr = yesterday.strftime("%Y%m%d %H:%M")

    # Get water level data
    WaterLevel = stationdata.get_data(
        begin_date=yesterdaystr,
        end_date=todaystr,
        product="water_level",
        datum="MLLW",
        time_zone="lst_ldt")

    return WaterLevel

def plotOwletData():
    # Define the file pattern you're looking for
    # Define the file pattern you're looking for
    file_pattern = 'owlet_data_*.csv'

    # Use glob to list files that match the pattern
    matching_files = glob.glob(file_pattern)

    # Check if there are matching files
    if len(matching_files) > 0:
        # Read the first matching file and store its contents in a DataFrame named 'df'
        first_matching_file = matching_files[0]
        df = pd.read_csv(first_matching_file)
        print(f'Reading file: {first_matching_file}')
        # Perform your data analysis or processing here using 'df'
        # Get data from csv
        # Get last 24 hours of data
        # Find the index where the session starts (assuming a session starts after a gap of at least one hour)
        session_start_index = 0

        for i in range(1, len(df)):
            time_diff = (pd.to_datetime(df['timestamp'][i]) - pd.to_datetime(df['timestamp'][i - 1])).total_seconds()
            if time_diff >= 3600:  # Check if the time difference is at least one hour
                session_start_index = i

        # Slice the DataFrame to get data only from the session
        df = df.iloc[session_start_index:]

        # Get time, heart rate, oxygen level, and movement
        time = df['timestamp']
        hr = df['hr']
        ox = df['ox']
        mv = df['mv']

        # Create Plot
        fig, axs = plt.subplots(1, 3, figsize=(12, 4))

        # Plot Heart Rate
        axs[0].plot(time, hr, color='black')
        axs[0].set_ylabel('Heart Rate')
        axs[0].set_xlabel('Time')

        # Plot Oxygen Level
        axs[1].plot(time, ox, color='black')
        axs[1].set_ylabel('Oxygen Level')
        axs[1].set_xlabel('Time')

        # Plot Movement
        axs[2].plot(time, mv, color='black')
        axs[2].set_ylabel('Movement')
        axs[2].set_xlabel('Time')

        # Limit the number of time points displayed on the x-axis
        num_displayed_ticks = 8  # Adjust this value as needed
        tick_positions = range(0, len(time), len(time) // num_displayed_ticks)
        tick_labels = [t.split()[1].rsplit(':', 1)[0] for i, t in enumerate(time) if
                       i in tick_positions]  # Extract HH:MM
        for ax in axs:
            ax.set_xticks(tick_positions)
            ax.set_xticklabels(tick_labels, rotation=45)  # Rotate x-axis labels for readability

        # Adjust spacing between subplots
        plt.tight_layout()

        # Save the figure
        plt.savefig('images/OwletData.png', dpi=60)
    else:
        print('No matching files found.')

    #plt.show()

# Plot last 24 hours of tide
def plotTide(TideData):
    # Adjust data for negative values
    minlevel = TideData['water_level'].min()
    TideData['water_level'] = TideData['water_level'] - minlevel

    # Create Plot
    fig, axs = plt.subplots(figsize=(12, 4))
    TideData['water_level'].plot.area(ax=axs, color='black')
    plt.title('Tide- Past 24 Hours', fontsize=20)
    #fontweight="bold",
    #axs.xaxis.set_tick_params(labelsize=20)
    #axs.yaxis.set_tick_params(labelsize=20)
    plt.savefig('images/TideLevel.png', dpi=60)
    #plt.show()


# Get High and Low tide info
def HiLo(StationID):
    # Create Station Object
    stationdata = nc.Station(StationID)

    # Get today date string
    today = dt.datetime.now()
    todaystr = today.strftime("%Y%m%d")
    # Get yesterday date string
    tomorrow = today + dt.timedelta(days=1)
    tomorrowstr = tomorrow.strftime("%Y%m%d")

    # Get Hi and Lo Tide info
    TideHiLo = stationdata.get_data(
        begin_date=todaystr,
        end_date=tomorrowstr,
        product="predictions",
        datum="MLLW",
        interval="hilo",
        time_zone="lst_ldt")

    return TideHiLo


# Set the font sizes
font15 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 15)
font20 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 20)
font22 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 22)
font30 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 30)
font35 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 35)
font50 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 50)
font60 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 60)
font100 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 100)
font160 = ImageFont.truetype(os.path.join(fontdir, 'Font.ttc'), 160)

# Set the colors
black = 'rgb(0,0,0)'
white = 'rgb(255,255,255)'
grey = 'rgb(235,235,235)'

# Function to update weather data
def update_weather_data():
    while True:
        try:
            # Get weather data
            data = getWeather(URL)

            # get current dict block
            current = data['current']
            # get current
            temp_current = current['temp']
            # get feels like
            feels_like = current['feels_like']
            # get humidity
            humidity = current['humidity']
            # get pressure
            wind = current['wind_speed']
            # get description
            weather = current['weather']
            report = weather[0]['description']
            # get icon url
            icon_code = weather[0]['icon']

            # get daily dict block
            daily = data['daily']
            # get daily precip
            daily_precip_float = daily[0]['pop']
            # format daily precip
            daily_precip_percent = daily_precip_float * 100
            # get min and max temp
            daily_temp = daily[0]['temp']
            temp_max = daily_temp['max']
            temp_min = daily_temp['min']

            # Set strings to be printed to screen
            string_location = LOCATION
            string_temp_current = format(temp_current, '.0f') + u'\N{DEGREE SIGN}F'
            string_feels_like = 'Feels like: ' + format(feels_like, '.0f') + u'\N{DEGREE SIGN}F'
            string_humidity = 'Humidity: ' + str(humidity) + '%'
            string_wind = 'Wind: ' + format(wind, '.1f') + ' MPH'
            string_report = 'Now: ' + report.title()
            string_temp_max = 'High: ' + format(temp_max, '>.0f') + u'\N{DEGREE SIGN}F'
            string_temp_min = 'Low:  ' + format(temp_min, '>.0f') + u'\N{DEGREE SIGN}F'
            string_precip_percent = 'Precip: ' + str(format(daily_precip_percent, '.0f')) + '%'

            # get min and max temp
            nx_daily_temp = daily[1]['temp']
            nx_temp_max = nx_daily_temp['max']
            nx_temp_min = nx_daily_temp['min']
            # get daily precip
            nx_daily_precip_float = daily[1]['pop']
            # format daily precip
            nx_daily_precip_percent = nx_daily_precip_float * 100

            # get min and max temp
            nx_nx_daily_temp = daily[2]['temp']
            nx_nx_temp_max = nx_nx_daily_temp['max']
            nx_nx_temp_min = nx_nx_daily_temp['min']
            # get daily precip
            nx_nx_daily_precip_float = daily[2]['pop']
            # format daily precip
            nx_nx_daily_precip_percent = nx_nx_daily_precip_float * 100

            # Tomorrow Forcast Strings
            nx_day_high = 'High: ' + format(nx_temp_max, '>.0f') + u'\N{DEGREE SIGN}F'
            nx_day_low = 'Low: ' + format(nx_temp_min, '>.0f') + u'\N{DEGREE SIGN}F'
            nx_precip_percent = 'Precip: ' + str(format(nx_daily_precip_percent, '.0f')) + '%'
            nx_weather_icon = daily[1]['weather']
            nx_icon = nx_weather_icon[0]['icon']

            # Overmorrow Forcast Strings
            nx_nx_day_high = 'High: ' + format(nx_nx_temp_max, '>.0f') + u'\N{DEGREE SIGN}F'
            nx_nx_day_low = 'Low: ' + format(nx_nx_temp_min, '>.0f') + u'\N{DEGREE SIGN}F'
            nx_nx_precip_percent = 'Precip: ' + str(format(nx_nx_daily_precip_percent, '.0f')) + '%'
            nx_nx_weather_icon = daily[2]['weather']
            nx_nx_icon = nx_nx_weather_icon[0]['icon']

            # Last updated time
            now = dt.datetime.now()
            current_time = now.strftime("%H:%M")
            last_update_string = 'Last Updated: ' + current_time

            # Current weather
            ## Open icon file
            icon_file = icon_code + '.png'
            icon_image = Image.open(os.path.join(icondir, icon_file))
            icon_image = icon_image.resize((130, 130))
            template.paste(icon_image, (50, 50))

            draw.text((25, 10), LOCATION, font=font35, fill=black)

            # Center current weather report
            w, h = draw.textsize(string_report, font=font20)
            # print(w)
            if w > 250:
                string_report = 'Now:\n' + report.title()

            center = int(120 - (w / 2))
            draw.text((center, 175), string_report, font=font20, fill=black)

            # Data
            draw.text((250, 55), string_temp_current, font=font35, fill=black)
            y = 100
            draw.text((250, y), string_feels_like, font=font15, fill=black)
            draw.text((250, y + 20), string_wind, font=font15, fill=black)
            draw.text((250, y + 40), string_precip_percent, font=font15, fill=black)
            draw.text((250, y + 60), string_temp_max, font=font15, fill=black)
            draw.text((250, y + 80), string_temp_min, font=font15, fill=black)

            draw.text((125, 218), last_update_string, font=font15, fill=black)

            # Weather Forcast
            # Tomorrow
            icon_file = nx_icon + '.png'
            icon_image = Image.open(os.path.join(icondir, icon_file))
            icon_image = icon_image.resize((130, 130))
            template.paste(icon_image, (435, 50))
            draw.text((450, 20), 'Tomorrow', font=font22, fill=black)
            draw.text((415, 180), nx_day_high, font=font15, fill=black)
            draw.text((515, 180), nx_day_low, font=font15, fill=black)
            draw.text((460, 200), nx_precip_percent, font=font15, fill=black)

            # Next Next Day Forcast
            icon_file = nx_nx_icon + '.png'
            icon_image = Image.open(os.path.join(icondir, icon_file))
            icon_image = icon_image.resize((130, 130))
            template.paste(icon_image, (635, 50))
            draw.text((625, 20), 'Next-Next Day', font=font22, fill=black)
            draw.text((615, 180), nx_nx_day_high, font=font15, fill=black)
            draw.text((715, 180), nx_nx_day_low, font=font15, fill=black)
            draw.text((660, 200), nx_nx_precip_percent, font=font15, fill=black)

            time.sleep(WEATHER_UPDATE_INTERVAL)  # Sleep for the update interval
        except Exception as e:
            print("Error updating weather data:", e)
            time.sleep(WEATHER_UPDATE_INTERVAL)  # Sleep even if there is an error

# Function to check owlet data transmission
def check_owlet_data():
    while True:
        try:
            # Check if owlet is transmitting data (you may need to modify this logic)
            owlet_transmitting = owlet_monitor.check_transmission()

            if owlet_transmitting:
                print("Owlet is transmitting data, updating every 10 seconds...")
                plotOwletData()
                time.sleep(OWLET_CHECK_INTERVAL)
            else:
                print("Owlet is not transmitting data, checking again in 10 seconds...")
                time.sleep(OWLET_CHECK_INTERVAL)
        except Exception as e:
            print("Error checking owlet data:", e)
            time.sleep(OWLET_CHECK_INTERVAL)  # Sleep even if there is an error

# Start the weather data update thread
weather_thread = threading.Thread(target=update_weather_data)
weather_thread.daemon = True
weather_thread.start()

# Start the owlet data check thread
owlet_thread = threading.Thread(target=check_owlet_data)
owlet_thread.daemon = True
owlet_thread.start()

'''
****************************************************************

Main Loop

****************************************************************
'''

# Initialize and clear screen
print('Initializing and clearing screen.')
try:
    epd = epd7in5_V2.EPD() # Create object for display functions
    epd.init()
    epd.Clear()
except:
    print('No EPD module found, falling back to console print')

while True:


    # Tide Data
    # Get water level
    # wl_error = True
    # while wl_error == True:
    #     try:
    #         WaterLevel = past24(StationID)
    #         wl_error = False
    #     except:
    #         display_error('Tide Data')

    plotOwletData()
    # plotTide(WaterLevel)


    # Open template file
    template = Image.open(os.path.join(picdir, 'template.png'))
    # Initialize the drawing context with template as background
    draw = ImageDraw.Draw(template)




    ## Dividing lines
    draw.line((400,10,400,220), fill='black', width=3)
    draw.line((600,20,600,210), fill='black', width=2)


    # Owlet Info
    # Graph
    tidegraph = Image.open('images/OwletData.png')
    template.paste(tidegraph, (25, 240))

    # Large horizontal dividing line
    h = 240
    draw.line((25, h, 775, h), fill='black', width=3)

    # Daily tide times
    # draw.text((30,260), "Today's Tide", font=font22, fill=black)

    # # Get tide time predictions
    # hilo_error = True
    # while hilo_error == True:
    #     try:
    #         hilo_daily = HiLo(StationID)
    #         hilo_error = False
    #     except:
    #         display_error('Tide Prediction')
    #
    # # Display tide preditions
    # y_loc = 300 # starting location of list
    # # Iterate over preditions
    # for index, row in hilo_daily.iterrows():
    #     # For high tide
    #     if row['hi_lo'] == 'H':
    #         tide_time = index.strftime("%H:%M")
    #         tidestr = "High: " + tide_time
    #     # For low tide
    #     elif row['hi_lo'] == 'L':
    #         tide_time = index.strftime("%H:%M")
    #         tidestr = "Low:  " + tide_time
    #
    #     # Draw to display image
    #     draw.text((40,y_loc), tidestr, font=font15, fill=black)
    #     y_loc += 25 # This bumps the next prediction down a line


    # Save the image for display as PNG
    screen_output_file = os.path.join(picdir, 'screen_output.png')
    template.save(screen_output_file)
    # Close the template file
    template.close()

    write_to_screen(screen_output_file, 60)
    #epd.Clear()

# TODO Every 10 minutes update weather
# TODO Check if owlet is transmitting data, if yes then update every 10 seconds if no then check for update