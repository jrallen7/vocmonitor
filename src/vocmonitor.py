#!/home/jrallen/env/bin/python3

import datetime
import os
import sys
import tomllib
from time import sleep, time
import sqlite3

import argparse
import adafruit_sgp40
import adafruit_sht4x
import adafruit_ssd1306
import board
import digitalio
from adafruit_sgp40.voc_algorithm import VOCAlgorithm
from PIL import Image, ImageDraw, ImageFont


class TempSensor:
    def __init__(self, i2c, skipinit=True):
        print("SHT41: Initializing")
        self._sht = adafruit_sht4x.SHT4x(i2c)
        self.reset()

        print(f"SHT41: Serial Number {hex(self._sht.serial_number)}")
        if not skipinit:
            self._sht.mode = adafruit_sht4x.Mode.HIGHHEAT_1S
            print(
                f"SHT41: Doing 5 heat pulses {adafruit_sht4x.Mode.string[self._sht.mode]}"
            )
            for _ in range(5):
                tempc, rh = self.measure()
                print(f"\tTemp: {tempc:.1f} RH: {rh:.0f}")
                sleep(1)
        self._sht.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
        print(
            f"SHT41: Measurement mode set to {adafruit_sht4x.Mode.string[self._sht.mode]}"
        )

    def measure(self):
        return self._sht.measurements

    def reset(self):
        self._sht.reset()


class VOCSensor:
    def __init__(self, i2cbus, skipinit=False):
        print("SGP40: Initializing")
        self._sgp = adafruit_sgp40.SGP40(i2cbus)
        self._vocalgorithm = VOCAlgorithm()
        self._vocalgorithm.vocalgorithm_init()

        if not skipinit:
            # initial measurement just to get the sensor running
            print("SGP40: Running 5 init measurements")
            for i in range(5):
                _ = self._sgp.measure_raw()
        print("SGP40: Done")

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
        print("Display: Initializing...", end="")
        self._disp = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)
        self._enabled = True

        # reduce display brightness
        self._disp.write_cmd(0xDB)
        self._disp.write_cmd(0b0001)
        self._disp.write_cmd(0xD9)
        self._disp.write_cmd(0b0001 << 4 | 0b1111)
        self._disp.contrast(2)

        self._image = Image.new("1", (self._disp.width, self._disp.height))
        self._draw = ImageDraw.Draw(self._image)
        self._fonts = {
            12: ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12
            ),
            16: ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 16
            ),
            14: ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14
            ),
        }

        self.clear()
        print()

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, en):
        if self._enabled != en:
            self._enabled = en
            if not self._enabled:
                self.clear()

    def clear_buffer(self):
        self._draw.rectangle(
            (0, 0, self._disp.width, self._disp.height), outline=0, fill=0
        )

    def update(self):
        self._disp.image(self._image)
        self._disp.show()

    def clear(self):
        self.clear_buffer()
        self.update()

    def add_text(self, xypos, text, fontsize):
        self._draw.text(xypos, text, font=self._fonts[fontsize], fill=255)


class FanControl:
    def __init__(self):
        self._pin = digitalio.DigitalInOut(board.D24)
        self._pin.direction = digitalio.Direction.OUTPUT
        self._pin.value = False
        self._enabled = False

        print("Fan Init:")
        self.enabled = True
        sleep(1)
        self.enabled = False

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, en):
        if self._enabled != en:
            print(f"Changing Fan State: {en}")
            self._enabled = en
            self._pin.value = self._enabled


def update(now):
    tempc, rh = tempsensor.measure()
    vocraw, vocindex = vocsensor.measure(tempc, rh)

    # Turn filter on if VOC high, only check every 5 seconds
    if now.second % 5 == 0:
        if vocindex >= 150 and not fan.enabled:
            fan.enabled = True
        elif vocindex < 140 and fan.enabled:
            fan.enabled = False

    timedatestring = now.astimezone().isoformat(timespec="milliseconds")
    tempstring = f"T {tempc:.0f} RH {rh:.0f}"
    vocstring = f"V {vocraw} {vocindex}"
    filterstring = f"F {fan.enabled}"

    display.clear_buffer()
    display.add_text((0, 0), tempstring, 16)
    display.add_text((0, 17), vocstring, 16)
    display.update()

    logstring = " ".join([timedatestring, tempstring, vocstring, filterstring])
    print(logstring)

    dbcur.execute(
        "INSERT INTO vocmonitor VALUES(?,?,?,?,?,?)",
        [timedatestring, tempc, rh, vocraw, vocindex, fan.enabled],
    )
    dbcon.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--initdb", action="store_true")
    parser.add_argument("--skipinit", action="store_true")
    args = parser.parse_args()

    pathroot = os.path.normpath(os.path.join(sys.path[0], ".."))
    pathuser = os.path.expanduser("~")

    with open(os.path.join(pathroot, "config.toml"), "rb") as f:
        configdata = tomllib.load(f)

    # initialize devices
    i2cbus = board.I2C()
    tempsensor = TempSensor(i2cbus, args.skipinit)
    vocsensor = VOCSensor(i2cbus, args.skipinit)
    display = Display(i2cbus)

    fan = FanControl()

    print("Connecting to database...", end="")
    dbcon = sqlite3.connect(os.path.join(pathuser, "test.db"))
    dbcur = dbcon.cursor()

    if args.initdb:
        print("Reinitializing VOC table")
        dbcur.execute("DROP TABLE IF EXISTS vocmonitor")
        dbcur.execute(
            "CREATE TABLE vocmonitor(time TEXT, temp REAL, rh REAL, vocraw INTEGER, vocindex INTEGER, filter INTEGER)"
        )
    else:
        print()

    try:
        while True:
            tpreupdate = time()
            update(datetime.datetime.now())
            tpostupdate = time()

            dtime = 1.0 - 0.0002 - (tpostupdate - tpreupdate)
            print(f"{dtime:0.3f}")
            if dtime > 0:
                sleep(dtime)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nShutting down...")
        print("Closing database")
        dbcon.commit()
        dbcon.close()
        print("Turning Fan Off")
        fan.enabled = False
        while not i2cbus.try_lock():
            pass
        i2cbus.unlock()
        tempsensor.reset()
        print("SGP40: Turning heater off...")
        vocsensor.turn_heater_off()
        print("Display: Clearing")
        display.clear()
