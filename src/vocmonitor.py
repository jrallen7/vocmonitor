#!/home/jrallen/adafruit/bin/python3

import asyncio
import datetime
import os
import sys
import tomllib
from time import sleep, time

import adafruit_sgp40
import adafruit_sht4x
import adafruit_ssd1306
import board
import memcache
from adafruit_sgp40.voc_algorithm import VOCAlgorithm
from kasa import Discover
from PIL import Image, ImageDraw, ImageFont


class TempSensor:
    def __init__(self, i2c):
        print("SHT41: Initializing")
        self._sht = adafruit_sht4x.SHT4x(i2c)
        self._sht.reset()

        print(f"SHT41: Serial Number {hex(self._sht.serial_number)}")
        print("SHT41: Initial measurement (one second, high heat)...", end="")
        self._sht.mode = adafruit_sht4x.Mode.HIGHHEAT_1S
        tempc, rh = self.measure()
        print(f"Temp: {tempc:.1f} RH: {rh:.0f}")

        self._sht.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
        print(
            f"SHT41: Measurement mode set to {adafruit_sht4x.Mode.string[self._sht.mode]}"
        )

    def measure(self):
        tempc, rh = self._sht.measurements
        return tempc, rh


class VOCSensor:
    def __init__(self, i2c):
        print("SGP40: Initializing")
        self._sgp = adafruit_sgp40.SGP40(i2c)
        self._vocalgorithm = VOCAlgorithm()
        self._vocalgorithm.vocalgorithm_init()
        # initial measurement just to get the sensor running
        print("SGP40: Running 5 measurements")
        for i in range(5):
            trash = self._sgp.measure_raw()
        # print('SGP40: Seeding Algorithm History')
        # self.seedhistory()
        print("SGP40: Done")

    # def __del__(self):

    def turn_heater_off(self):
        self._sgp._command_buffer[0] = 0x36
        self._sgp._command_buffer[1] = 0x15
        self._sgp._read_word_from_command(readlen=None)

    def measure(self, tempc=25.0, rh=50.0):
        vocraw = self._sgp.measure_raw(temperature=tempc, relative_humidity=rh)
        vocindex = self._vocalgorithm.vocalgorithm_process(vocraw)
        return vocraw, vocindex

    def seedhistory(self):
        n = datetime.datetime.now()
        ii = 0
        for dd in [-1, 0]:
            logfname = (n + datetime.timedelta(days=dd)).strftime("%Y-%m-%d.log")
            with open(os.path.join(sys.path[0], "logs", logfname), "rt") as fi:
                for l in fi:
                    l = l.strip().split()
                    try:
                        i = l.index("V")
                        vraw = int(l[i + 1])
                        if vraw != 0:
                            vocindex = self._vocalgorithm.vocalgorithm_process(vraw)
                            ii += 1
                            #                    print(ii)
                            if ii % 100 == 0:
                                print(".", end="", flush=True)
                    except ValueError:
                        pass
        print(f"Seeded {ii} Values")


class Display:
    def __init__(self, i2c):
        print("Display: Initializing...", end="")
        self._disp = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)
        self._disp.contrast(1)
        self.clear()
        self._enabled = False

        self._image = Image.new("1", (self._disp.width, self._disp.height))
        self._draw = ImageDraw.Draw(self._image)
        self._font1 = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12
        )
        self._font2 = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 16
        )
        print()

    # def __del__(self):

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, en):
        if self._enabled != en:
            self._enabled = en
            if not self._enabled:
                self.clear()

    def clear(self):
        self._disp.fill(0)
        self._disp.show()

    def writedata(self, tempc, rh, vocraw, vocindex):
        if self._enabled:
            # Generate blank rectangle image
            self._draw.rectangle(
                (0, 0, self._disp.width, self._disp.height), outline=0, fill=0
            )

            # Add text
            self._draw.text((0, 1), f"T {tempc:.0f}C", font=self._font1, fill=255)
            self._draw.text((80, 1), f"RH {rh:.0f}", font=self._font1, fill=255)
            self._draw.text(
                (0, 17), f"VOC {vocraw:5d} {vocindex:3d}", font=self._font2, fill=255
            )

            # Push image to display
            self._disp.image(self._image)
            self._disp.show()


def update(now):
    tempc, rh = tempsensor.measure()
    vocraw, vocindex = vocsensor.measure(tempc, rh)

    # Display only on for 2 out of 10 seconds to prevent aging
    if now.second % 10 < 2:
        display.enabled = True
    else:
        display.enabled = False
    display.writedata(tempc, rh, vocraw, vocindex)

    # Turn filter on if VOC high, only check every 5 seconds
    if now.second % 5 == 0:
        filteron = shared.get("filter")
        if vocindex >= 150 and filteron == 0:
            asyncioloop.run_until_complete(kasaswitch.turn_on())
            shared.set("filter", 1)
        elif vocindex < 150 and filteron == 1:
            asyncioloop.run_until_complete(kasaswitch.turn_off())
            shared.set("filter", 0)

    timedatestring = now.astimezone().isoformat(timespec="milliseconds")
    tempstring = f"T {tempc:.1f} RH {rh:.1f}"
    vocstring = f"V {vocraw} {vocindex}"
    filterstring = f'F {shared.get("filter")}'
    printerstring = (
        f"P {shared.get('temp_hotend'):.1f} {shared.get('temp_hotend_tgt'):.1f} "
        + f"{shared.get('temp_bed'):.1f} {shared.get('temp_bed_tgt'):.1f} "
        + f"{shared.get('status')} {shared.get('printpct')}"
    )
    logstring = " ".join(
        [timedatestring, tempstring, vocstring, filterstring, printerstring]
    )
    print(logstring)
    with open(os.path.join(pathlogs, now.strftime("%Y-%m-%d.log")), "at") as fo:
        fo.write(f"{logstring}\n")


if __name__ == "__main__":
    pathroot = os.path.normpath(os.path.join(sys.path[0], ".."))
    pathlogs = os.path.join(pathroot, "logs")

    with open(os.path.join(pathroot, "config.toml"), "rb") as f:
        configdata = tomllib.load(f)

    shared = memcache.Client([configdata["memcache"]["ip"]], debug=0)
    try:
        asyncioloop = asyncio.get_running_loop()
    except RuntimeError:
        asyncioloop = asyncio.new_event_loop()
    asyncio.set_event_loop(asyncioloop)

    # initialize devices
    i2c = board.I2C()
    tempsensor = TempSensor(i2c)
    vocsensor = VOCSensor(i2c)
    display = Display(i2c)
    kasaswitch = asyncioloop.run_until_complete(
        Discover.discover_single(
            host=configdata["kasa"]["host"],
            username=configdata["kasa"]["username"],
            password=configdata["kasa"]["password"],
        )
    )
    asyncioloop.run_until_complete(kasaswitch.update())
    asyncioloop.run_until_complete(kasaswitch.turn_off())
    shared.set("filter", 0)

    try:
        while True:
            tpreupdate = time()

            now = datetime.datetime.now()

            update(now)
            # tpostupdate = datetime.datetime.now()

            dtime = 1.0 - (time() - tpreupdate)
            if dtime > 0:
                sleep(dtime)
    except KeyboardInterrupt:
        pass
    finally:
        print("Shutting down...")
        print("SGP40: Turning heater off...")
        vocsensor.turn_heater_off()
        print("Turning off Kasa switch")
        asyncioloop.run_until_complete(kasaswitch.turn_off())
        asyncioloop.run_until_complete(kasaswitch.disconnect())
        print("Display: Clearing")
        display.clear()
