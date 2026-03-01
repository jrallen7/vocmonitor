#!/home/jrallen/adafruit/bin/python3

# builtins
import board, datetime, os, tomllib, asyncio
from time import sleep

# external libraries
from PIL import Image, ImageDraw, ImageFont
from kasa import Discover
import adafruit_sht4x, adafruit_sgp40, adafruit_ssd1306
from adafruit_sgp40.voc_algorithm import VOCAlgorithm
import memcache

shared = memcache.Client(['127.0.0.1:11211'], debug=0)


class TempSensor:
    def __init__(self, i2c):
        print('SHT41: Initializing')
        self._sht = adafruit_sht4x.SHT4x(i2c)
        self._sht.reset()
        print(f'SHT41: Serial Number {hex(self._sht.serial_number)}')

        print('SHT41: One second high heat measurement...', end='')
        self._sht.mode = adafruit_sht4x.Mode.HIGHHEAT_1S
        tempc, rh = self.measure()
        print(f'Temp: {tempc:.1f} RH: {rh:.0f}')

        self._sht.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
        print(f'SHT41: Mode is {adafruit_sht4x.Mode.string[self._sht.mode]}')

    def measure(self):
        tempc, rh = self._sht.measurements
        return tempc, rh


class VOCSensor:
    def __init__(self, i2c):
        print('SGP40: Initializing')
        self._sgp = adafruit_sgp40.SGP40(i2c)
        self._vocalgorithm = VOCAlgorithm()
        self._vocalgorithm.vocalgorithm_init()

    def __del__(self):
        print('SGP40: Turning heater off...')
        self.turn_heater_off()

    def turn_heater_off(self):
        self._sgp._command_buffer[0] = 0x36
        self._sgp._command_buffer[1] = 0x15
        self._sgp._read_word_from_command(readlen=None)

    def measure(self, tempc=25.0, rh=50.0):
        vocraw = self._sgp.measure_raw(temperature=tempc, relative_humidity=rh)
        vocindex = self._vocalgorithm.vocalgorithm_process(vocraw)
        return vocraw, vocindex


class Display:
    def __init__(self, i2c):
        print('Display: Initializing...')
        self._disp = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)
        self._disp.contrast(1)
        self.clear()
        self._enabled = False

        self._image = Image.new('1', (self._disp.width, self._disp.height))
        self._draw = ImageDraw.Draw(self._image)
        self._font1 = ImageFont.truetype('/usr/share/fonts/truetype/' +
                                         'dejavu/DejaVuSansMono.ttf', 12)
        self._font2 = ImageFont.truetype('/usr/share/fonts/truetype/' +
                                         'dejavu/DejaVuSansMono.ttf', 16)
        print()

    def __del__(self):
        print('Clearing display...')
        self.clear()

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, v):
        if self._enabled != v:
            self._enabled = v
            if not self._enabled:
                self.clear()

    def clear(self):
        self._disp.fill(0)
        self._disp.show()

    def update(self, tempc, rh, vocraw, vocindex):
        if self._enabled:
            # Generate blank rectangle image
            self._draw.rectangle((0, 0, self._disp.width, self._disp.height),
                                 outline=0, fill=0)

            # Add text
            self._draw.text((0, 1), f'T {tempc:.0f}C',
                            font=self._font1, fill=255)
            self._draw.text((80, 1), f'RH {rh:.0f}',
                            font=self._font1, fill=255)
            self._draw.text((0, 17), f'VOC {vocraw:5d} {vocindex:3d}',
                            font=self._font2, fill=255)

            # Push image to display
            self._disp.image(self._image)
            self._disp.show()


async def update(now):
    tempc, rh = tempsensor.measure()
    vocraw, vocindex = vocsensor.measure(tempc, rh)

    #Display only on for 2 out of 10 seconds to prevent aging
    if now.second % 10 < 2:
        display.enabled = True
    else:
        display.enabled = False
    display.update(tempc, rh, vocraw, vocindex)

    #Turn filter on if VOC high, only check every 5 seconds
    if now.second % 5 == 0:
        if vocindex > 150:
            await kasaswitch.turn_on()
            shared.set('filter', 1)
        else:
            await kasaswitch.turn_off()
            shared.set('filter', 0)

    timedatestring = now.astimezone().isoformat(timespec='milliseconds')
    tempstring = f'T {tempc:.1f} RH {rh:.1f}'
    vocstring = f'V {vocraw} {vocindex}'
    filterstring = f'F {shared.get("filter")}'
    #printerstring = f'P {shared.get("temp_bed")} {shared.get("temphotend")}'
    printerstring = f'P {shared.get("temp_hotend"):.1f} {shared.get("temp_hotend_tgt"):.1f} ' + \
            f'{shared.get("temp_bed"):.1f} {shared.get("temp_bed_tgt"):.1f} ' + \
          f'{shared.get("status")} {shared.get("printpct")}'
    logstring = ' '.join([timedatestring, tempstring, vocstring, filterstring, printerstring])
    print(logstring)
    with open(os.path.join(os.getcwd(), 'logs', now.strftime('%Y-%m-%d.log')), 'at') as fo:
        fo.write(f'{logstring}\n')




async def main():
    global kasaswitch, tempsensor, vocsensor, display, bambu_client

    with open ('.vocconfig.toml', 'rb') as f:
        configdata = tomllib.load(f)

    # initialize devices
    i2c = board.I2C()
    tempsensor = TempSensor(i2c)
    vocsensor = VOCSensor(i2c)
    display = Display(i2c)

    kasaswitch = await Discover.discover_single(host=configdata['kasa']['ip'],
                                                username=configdata['kasa']['id'],
                                                password=configdata['kasa']['pass'])
    await kasaswitch.update()
    await kasaswitch.turn_off()
    shared.set('filter', 0)

    while True:
        if os.path.exists('vocstop'):
            break

        tpreupdate = datetime.datetime.now()
        await update(tpreupdate)
        tpostupdate = datetime.datetime.now()

        dtime = 1.0 - (tpostupdate - tpreupdate).total_seconds()
        sleep(dtime)

    print('Shutting down...')
    print('Turning off Kasa switch')
    await kasaswitch.turn_off()
    await kasaswitch.disconnect()
    os.remove('vocstop')


if __name__ == '__main__':
    asyncio.run(main())
