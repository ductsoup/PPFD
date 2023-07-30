from time import sleep
import board
import busio
from Adafruit_IO import MQTTClient

#from adafruit_as7341 import AS7341, Gain
from adafruit_as7341 import *
import adafruit_as7341
import adafruit_tsl2591
import adafruit_bh1750
import adafruit_ltr390
import adafruit_bme680
import adafruit_scd4x

def bar_graph(read_value):
    scaled = int(read_value / 1000)
    return "[%6d] " % read_value + (scaled * "*")

#try:
'''
Initialize AIO
https://github.com/adafruit/Adafruit_CircuitPython_AdafruitIO
https://forums.adafruit.com/viewtopic.php?f=19&t=174427&p=851155&hilit=as7341#p851155
'''
ADAFRUIT_IO_KEY = 'your information here'
ADAFRUIT_IO_USERNAME = 'your information here'
aio = MQTTClient(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)
aio.connect()
aio.loop_background()
aio_update = 60 # update interval in seconds 
aio_current = 61

i2c = busio.I2C(board.SCL, board.SDA)
    
'''
https://forums.adafruit.com/viewtopic.php?f=19&t=174427&p=851155&hilit=as7341#p851155
'''

class AS7341X(AS7341):
    """
    Extend the base class to read all the channels and perform a reliable autogain
    """
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

# Initialize the AS7341
s_as7341 = AS7341X(i2c)   
s_as7341.disable_agc()
s_as7341.gain = Gain.GAIN_16X   # start in the middle
s_as7341.atime = 9              # set the integration time to 27.8ms
s_as7341.astep = 999
 
''' 
https://www.adafruit.com/product/4698
https://ams.com/documents/20143/36005/AS7341_DS000504_3-00.pdf/
https://github.com/adafruit/Adafruit_CircuitPython_AS7341
("GAIN_0_5X", 0, 0.5, None),
("GAIN_1X", 1, 1, None),
("GAIN_2X", 2, 2, None),
("GAIN_4X", 3, 4, None),
("GAIN_8X", 4, 8, None),
("GAIN_16X", 5, 16, None),
("GAIN_32X", 6, 32, None),
("GAIN_64X", 7, 64, None),
("GAIN_128X", 8, 128, None),
("GAIN_256X", 9, 256, None),
("GAIN_512X", 10, 512, None),
sensor.gain = Gain.GAIN_512X
Integration time, in milliseconds, is equal to: (ATIME + 1) x (ASTEP + 1) x 2.78μs
astep = 599, atime = 29 = 50ms
    0 ~ 2.78us
    599 ~ 1.67ms
    999 ~ 2.78ms
    17999 ~ 50ms
    65534 ~ 182ms
ADCfullscale = (ATIME + 1) x (ASTEP + 1)
'''

class TSL2591X(adafruit_tsl2591.TSL2591):
    '''
    Description:
    Extend the tsl2591 class with auto-range to realize the full accuracy of the device across it's capable range, 
    and also report irradiance in more familiar/useful units.

    Usage:
        import board
        import busio
        import adafruit_tsl2591
        s_tsl2591 = TSL2591X(i2c)
        s_tsl2591.begin()

        # in a loop
        s_tsl2591.autorange()
        # the base class will throw an excpetion if the light is too bright and device becomes saturated
        try:
            print(s_tsl2591.lux)
            # the general rule of thumb is to use 0.0079 * lux for daylight to get W/m^2 so we use that as a sanity check
            print(0.0079 * s_tsl2591.lux, s_tsl2591.irradiance())
        except:
            pass

    Notes:
    channel_0 should probably never be less than channel_1 under normal circumstances so we set the gain and integration
    time based only on channel_0.

    There are 24 combinations of gain and integration time for this device. Most are not particularly useful for general
    applications so to simplify, we choose 7 that overlap neatly for a bumpless transition between states that also 
    enables access to the entire dynamic range of the device.

    Calculate the thresholds for 0.05 and 0.95 of the max range then pick your states.

    Gain Integration(ms)	Max	   ATM	  Lo	  Hi	    Rank Thresholds		
       1 100	            36863     100       5        95	1	 1,843 35,020
       1 200	            65535     200      10       190		 3,277 62,258
       1 300	            65535     300      15       285		 3,277 62,258
       1 400	            65535     400      20       380		 3,277 62,258
       1 500	            65535     500      25       475		 3,277 62,258
       1 600	            65535     600      30       570	2	 3,277 62,258
      25 100	            36863    2500     125     2,375		 1,843 35,020
      25 200            	65535    5000     250     4,750	3	 3,277 62,258
      25 300	            65535    7500     375     7,125		 3,277 62,258
      25 400	            65535   10000     500     9,500		 3,277 62,258
      25 500	            65535   12500     625    11,875		 3,277 62,258
      25 600	            65535   15000     750    14,250		 3,277 62,258
     428 100	            36863   42800   2,140    40,660	4	 1,843 35,020
     428 200	            65535   85600   4,280    81,320		 3,277 62,258
     428 300	            65535  128400   6,420	121,980		 3,277 62,258
     428 400	            65535  171200   8,560	162,640		 3,277 62,258
     428 500	            65535  214000  10,700	203,300		 3,277 62,258
     428 600	            65535  256800  12,840	243,960	5	 3,277 62,258
    9876 100	            36863  987600  49,380	938,220		 1,843 35,020
    9876 200	            65535 1975200  98,760 1,876,440	6	 3,277 62,258
    9876 300	            65535 2962800 148,140 2,814,660		 3,277 62,258
    9876 400	            65535 3950400 197,520 3,752,880		 3,277 62,258
    9876 500	            65535 4938000 246,900 4,461,100		 3,277 62,258
    9876 600	            65535 5925600 296,280 5,629,320	7	 3,277 62,258

    Reference:
    https://www.adafruit.com/product/1980       
    https://github.com/adafruit/Adafruit_CircuitPython_TSL2591
    https://cdn-learn.adafruit.com/assets/assets/000/078/658/original/TSL2591_DS000338_6-00.pdf?1564168468    
    https://github.com/adafruit/Adafruit_CircuitPython_TSL2591
    https://ams.com/documents/20143/36005/AmbientLightSensors_AN000171_2-00.pdf/9d1f1cd6-4b2d-1de7-368f-8b372f3d8517
    '''

    states = (
        {"gain": adafruit_tsl2591.GAIN_LOW,  "integration": adafruit_tsl2591.INTEGRATIONTIME_100MS, "lo":1843, "hi":35020},
        {"gain": adafruit_tsl2591.GAIN_LOW,  "integration": adafruit_tsl2591.INTEGRATIONTIME_600MS, "lo":3277, "hi":62258},
        {"gain": adafruit_tsl2591.GAIN_MED,  "integration": adafruit_tsl2591.INTEGRATIONTIME_200MS, "lo":3277, "hi":62258},
        {"gain": adafruit_tsl2591.GAIN_HIGH, "integration": adafruit_tsl2591.INTEGRATIONTIME_100MS, "lo":1843, "hi":35020},
        {"gain": adafruit_tsl2591.GAIN_HIGH, "integration": adafruit_tsl2591.INTEGRATIONTIME_600MS, "lo":3277, "hi":62258},
        {"gain": adafruit_tsl2591.GAIN_MAX,  "integration": adafruit_tsl2591.INTEGRATIONTIME_200MS, "lo":3277, "hi":62258},
        {"gain": adafruit_tsl2591.GAIN_MAX,  "integration": adafruit_tsl2591.INTEGRATIONTIME_600MS, "lo":3277, "hi":62258}
        )
    state = 0

    # rather than override __init__ in the base class just get the device and the class in sync
    def begin(self):
        self.setstate(self.state)

    def setstate(self, val):
        self.gain = self.states[val]['gain']
        self.integration_time = self.states[val]['integration']
        self.state = val
        sleep(1)            
 
    def autorange(self):
        while (True):
            channel_0, channel_1 = self.raw_luminosity
            # debug
            print(self.state, self.states[self.state]['lo'], self.states[self.state]['hi'])
            if channel_0 > self.states[self.state]['hi'] and self.state > 0:
                self.setstate(self.state - 1)
                continue
            elif channel_0 < self.states[self.state]['lo'] and self.state < 6:
                self.setstate(self.state + 1)
                continue
            else:
                pass
            # debug
            print("auto %dx @ %dms %d %d" % ([1, 25, 428, 9876][self.gain >> 4], 100*(self.integration_time + 1), channel_0, channel_1))
            break
    '''
    Estimate irradiance in W/m^2

    From the datasheet at GAIN_HIGH and 100MS:
        ch0 264.1 counts/(uW/cm^2)
        ch1  34.9 counts/(uW/cm^2)
    '''
    def irradiance(self):
        channel_0, channel_1 = self.raw_luminosity
        f = (428 / [1, 25, 428, 9876][self.gain >> 4]) * (1 / (self.integration_time + 1))
        return (f * channel_0 / 26410.0) 

s_tsl2591 = TSL2591X(i2c)
s_tsl2591.begin()


'''
https://www.adafruit.com/product/4681
https://www.mouser.com/datasheet/2/348/bh1750fvi-e-186247.pdf
https://github.com/adafruit/Adafruit_CircuitPython_BH1750
("SHUTDOWN", 0, "Shutdown", None),
("CONTINUOUS", 1, "Continuous", None),
("ONE_SHOT", 2, "One Shot", None),
("LOW", 3, "Low", None),  # 4 lx resolution "L-Resolution Mode" in DS
("MID", 0, "Mid", None),  # 1 lx resolution "H-Resolution Mode" in DS
("HIGH", 1, "High", None),  # 0.5 lx resolution, "H-Resolution Mode2" in D
self.mode = Mode.CONTINUOUS  # pylint:disable=no-member
self.resolution = Resolution.HIGH  # pylint:disable=no-member
'''
s_bh1750 = adafruit_bh1750.BH1750(i2c) 

'''
https://www.adafruit.com/product/4831
https://optoelectronics.liteon.com/upload/download/DS86-2015-0004/LTR-390UV_Final_%20DS_V1%201.pdf
https://github.com/adafruit/Adafruit_CircuitPython_LTR390
("GAIN_1X", 0, "1X", None),
("GAIN_3X", 1, "3X", None),
("GAIN_6X", 2, "6X", None),
("GAIN_9X", 3, "9X", None),
("GAIN_18X", 4, "18X", None)
("RESOLUTION_20BIT", 0, "20 bits", None),
("RESOLUTION_19BIT", 1, "19 bits", None),
("RESOLUTION_18BIT", 2, "18 bits", None),
("RESOLUTION_17BIT", 3, "17 bits", None),
("RESOLUTION_16BIT", 4, "16 bits", None),
("RESOLUTION_13BIT", 5, "13 bits", None),
("DELAY_25MS", 0, "25", None),
("DELAY_50MS", 1, "50", None),
("DELAY_100MS", 2, "100", None),
("DELAY_200MS", 3, "200", None),
("DELAY_500MS", 4, "500", None),
("DELAY_1000MS", 5, "1000", None),
("DELAY_2000MS", 6, "2000", None),
self.gain = Gain.GAIN_3X  # pylint:disable=no-member
self.resolution = Resolution.RESOLUTION_16BIT  # pylint:disable=no-member
'''

class LTR390X(adafruit_ltr390.LTR390):
    @property
    def lux(self):
        sgain = [1, 3, 6, 9, 18]
        sresint = [4, 2, 1, 0.5, .25, 0.03125]
        print("LTR390 gain", self.gain, "resolution", self.resolution)
        return (0.6 * self.light) / (sgain[self.gain] * sresint[self.resolution]) / 2

s_ltr390 = LTR390X(i2c)
#s_ltr390 = adafruit_ltr390.LTR390(i2c)

s_scd41 = adafruit_scd4x.SCD4X(i2c)
s_scd41.start_periodic_measurement()

while True:
    if aio_current < aio_update:
        aio_current += 1
    else:
        print("LTR390  - 320nm/UVA      %s" % bar_graph(s_ltr390.uvs))
        print("AS7341 Gain", s_as7341.gain)
        print("AS7341  - 415nm/Violet  %s" % bar_graph(s_as7341.channel_415nm))
        print("AS7341  - 445nm//Indigo %s" % bar_graph(s_as7341.channel_445nm))
        print("AS7341  - 480nm//Blue   %s" % bar_graph(s_as7341.channel_480nm))
        print("AS7341  - 515nm//Cyan   %s" % bar_graph(s_as7341.channel_515nm))
        print("AS7341  - 555nm/Green   %s" % bar_graph(s_as7341.channel_555nm))
        print("AS7341  - 590nm/Yellow  %s" % bar_graph(s_as7341.channel_590nm))
        print("AS7341  - 630nm/Orange  %s" % bar_graph(s_as7341.channel_630nm))
        print("AS7341  - 680nm/Red     %s" % bar_graph(s_as7341.channel_680nm))
        print("AS7341  - 910nm/NIR     %s" % bar_graph(s_as7341.channel_910nm))
        print("AS7341  - Clear         %s" % bar_graph(s_as7341.channel_clear))
        print()
        s_tsl2591.autorange()
        try:
            print(0.0079 * s_tsl2591.lux, s_tsl2591.irradiance())
            print(s_tsl2591.lux)
            #print("TSL2591 - RAW IR        [%6d]" % s_tsl2591.infrared)
            #print("TSL2591 - RAW Visible   [%5d]" % s_tsl2591.visible)
            print()
        except:
            pass
        print("BH1750  - LUX           %s" % bar_graph(s_bh1750.lux))
        print()
        print("\n------------------------------------------------")

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
        print(" Irradiance: %f (W m-2)" % IR)

        """ Check that AIO is connected """
        aio_current = 0
        if (not aio.is_connected()):
            aio._client.loop_stop()
            aio = MQTTClient(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)
            aio.connect()
            aio.loop_background()
        else:
            if s_scd41.data_ready:
                print("        CO2: %d (ppm)" % s_scd41.CO2)
                print("Temperature: %0.1f (C)" % s_scd41.temperature)
                print("   Humidity: %0.1f (%%)" % s_scd41.relative_humidity)
                aio.publish('LSA-CO2', s_scd41.CO2)
                aio.publish('LSA-T', s_scd41.temperature)
                aio.publish('LSA-RH', s_scd41.relative_humidity)

            aio.publish('LSA-320nm', s_ltr390.uvs)
            aio.publish('LSA-415nm', s_as7341.channel_415nm)
            aio.publish('LSA-445nm', s_as7341.channel_445nm)
            aio.publish('LSA-480nm', s_as7341.channel_480nm)
            aio.publish('LSA-515nm', s_as7341.channel_515nm)
            aio.publish('LSA-555nm', s_as7341.channel_555nm)
            aio.publish('LSA-590nm', s_as7341.channel_590nm)
            aio.publish('LSA-630nm', s_as7341.channel_630nm)
            aio.publish('LSA-680nm', s_as7341.channel_680nm)
            aio.publish('LSA-910nm', s_as7341._channel_5_data)
            aio.publish('LSA-CLEAR', s_as7341._channel_4_data)
            aio.publish('LSA-VISIBLE', s_as7341.channel_clear - s_as7341.channel_910nm)
            aio.publish('LSA-LUX1', s_tsl2591.lux)
            aio.publish('LSA-PPFD', PPFD)     
            aio.publish('LSA-IRRADIANCE2', IR)       

            try:
                aio.publish('LSA-LUX1-STATE', s_tsl2591.state)
                aio.publish('LSA-IRRADIANCE', s_tsl2591.irradiance())
            except:
                pass
            aio.publish('LSA-LUX2', s_bh1750.lux)
            aio.publish('LSA-LUX3', (s_ltr390.lux))

        """
        TSL2591 Lux: 50.161121
         BH1750 Lux: 47.500000
         LTR390 Lux: 46.800000

        TSL2591 Lux: 143.573568
         BH1750 Lux: 151.250000
         LTR390 Lux: 292.000000
        """
        print("TSL2591 Lux: %f" % s_tsl2591.lux)
        print(" BH1750 Lux: %f" % s_bh1750.lux)
        print(" LTR390 Lux: %f" % s_ltr390.lux) 
       
    sleep(1)
#except:
#    i2c.deinit()
