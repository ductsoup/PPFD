from time import sleep
import board
import busio
from adafruit_as7341 import *
import adafruit_as7341
import adafruit_scd4x

i2c = busio.I2C(board.SCL, board.SDA)
    
''' 
    Photosynthetic Photon Flux Density (PPFD) Measurement (poor man's quantum meter)

    Estimate PPFD and irradiance from 400 to 700nm.

    MIT License
    Copyright (c) 2022 Ductsoup
    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:
   
    The above copyright notice and this permission notice shall be included in
    all copies or substantial portions of the Software.
  
    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
    THE SOFTWARE.    
'''

"""
    AS7341 
    10-Channel Light / Color Sensor Breakout - STEMMA QT / Qwiic
    https://www.adafruit.com/product/4698
    https://learn.adafruit.com/adafruit-as7341-10-channel-light-color-sensor-breakout
    https://ams.com/documents/20143/36005/AS7341_DS000504_3-00.pdf/

    Extend the base class to read all the channels and perform a reliable autogain.
"""
class AS7341X(AS7341):
    @property
    def channel_910nm(self):
        """ The current reading for the 910nm channel """
        self._configure_f1_f4
        return self._channel_5_data

    @property
    def channel_clear(self):
        """ The current reading for the clear channel """
        self._configure_f1_f4
        return self._channel_4_data

    def disable_agc(self):
        self._write_register(0xA9, 0x00)        
        self._write_register(0xB1, 0b10000000) 
        return       

    def enable_agc(self):
        """ The built-in AGC feature is problematic so best not to use it for this """
        self._write_register(0xA9, 0x00)        
        self._write_register(0xB3, 0b10010010)
        self._write_register(0xB1, 0b10000100) 
        self.gain = Gain.GAIN_16X
        return     

    @property
    def autogain(self):
        """ Automatically adjust the gain then return all channels and the integration time """
        sgain = [
            Gain.GAIN_0_5X,
            Gain.GAIN_1X,
            Gain.GAIN_2X,
            Gain.GAIN_4X,
            Gain.GAIN_8X,
            Gain.GAIN_16X,
            Gain.GAIN_32X,
            Gain.GAIN_64X,
            Gain.GAIN_128X,
            Gain.GAIN_256X,
            Gain.GAIN_512X
            ]
        hysteresis = 0.2

        Fn = list(self.all_channels)
        Fn.append(self.channel_910nm)
        Fn.append(self.channel_clear)

        ADCfullscale = (self.atime + 1) * (self.astep + 1)
        while True: 
            if max(Fn) > (1 - hysteresis)*ADCfullscale and self.gain > 0:
                self.gain = sgain[self.gain - 1]
                print("* autorange: %dx" % Gain.string[self.gain])
                continue
            elif min(Fn) < (hysteresis)*ADCfullscale and self.gain < 10:
                self.gain = sgain[self.gain + 1]
                print("* autorange: %dx" % Gain.string[self.gain])
                continue
            else:
                break

        tint = ((self.atime + 1 ) * (self.astep + 1) * 2.78 / 1000)
        print("AS7341 gain: %dx (%d)" % (Gain.string[self.gain], self.gain), max(Fn), min(Fn))        
        print("      atime:", self.atime)
        print("      astep:", self.astep)
        print("       tint: %f (ms)" % tint)

        return Fn, tint

s_as7341 = AS7341X(i2c)   
s_as7341.disable_agc()
s_as7341.gain = Gain.GAIN_16X   # start in the middle
s_as7341.atime = 9              # set the integration time to 27.8ms
s_as7341.astep = 999

"""
    SCD-41 
    True CO2, Temperature and Humidity Sensor - STEMMA QT / Qwiic
    https://www.adafruit.com/product/5190
    https://learn.adafruit.com/adafruit-scd-40-and-scd-41
    https://cdn-learn.adafruit.com/assets/assets/000/104/015/original/Sensirion_CO2_Sensors_SCD4x_Datasheet.pdf?1629489682
"""
s_scd41 = adafruit_scd4x.SCD4X(i2c)
s_scd41.start_periodic_measurement()

update = 5              # update interval in seconds
current = update + 1

while True:
    if current < update:
        current += 1
    else:
        """ AS7341 PPFD """
        # Fetch the raw data from the AS7341
        Fn, tint = s_as7341.autogain

        # Constants from the datasheet calculated at @ gain = 1, atime = 100, astep = 999 (~ 280.78ms)
        a0 = 0.044204   
        a1 = 0.049516
        bn = (6.225412, 3.215098, 2.487901, 1.906658, 1.474367, 1.170204, 1.170686, 0.930505)
        print("         a0: %f" % a0)
        print("         a1: %f" % a1)
        
        # Scale for the measured spectral responsivity relative to F8
        PPFD = 0
        for i in range(0,8):
            print("         b%d: %f, F%d = %d" % (i+1, bn[i], i+1, Fn[i]))
            PPFD += bn[i] * Fn[i]
        PPFD = a0 * (PPFD + a1)

        # Scale for the current gain and integration time
        PPFD = PPFD * (280.78 / tint) * (1 / Gain.string[s_as7341.gain])
        print("       PPFD: %f (umol m-2 s-1)" % PPFD)
        
        """ AS7341 irradiance """
        # Constants the datasheet for irradiance
        cn = (55, 110, 210, 390, 590, 840, 1350, 1070)

        # Scale for F1 to F8 irradiance
        IR = 0
        for i in range(0,8):
            IR += 107.67 * Fn[i] / cn[i]

        # Scale for the current gain and integration time
        IR = IR * (280.78 / tint) * (1 / Gain.string[s_as7341.gain])
        # Convert units
        IR /= 10
        print(" Irradiance: %f (W m-2)" % (IR))

        if s_scd41.data_ready:
            print("        CO2: %d (ppm)" % s_scd41.CO2)
            print("Temperature: %0.1f (C)" % s_scd41.temperature)
            print("   Humidity: %0.1f (%%)" % s_scd41.relative_humidity)

        print()

        current = 0

    sleep(1)

i2c.deinit()
