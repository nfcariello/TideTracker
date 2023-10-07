from lib.waveshare_epd import epd7in5_V2

epd = epd7in5_V2.EPD() # Create object for display functions
epd.init()
epd.Clear()