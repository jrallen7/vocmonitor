#!/home/jrallen/adafruit/bin/python3

import tomllib
import sys
import os
from time import sleep

# external libraries
import memcache

# need to have the latest version of bambu-connect
# from github; the pip version doesn't have the latest bug fixes
sys.path.append(os.path.abspath('/home/jrallen/bambu-connect'))
from bambu_connect import BambuClient


def bambu_status_callback(statusmsg):
    if statusmsg.nozzle_target_temper is not None:
        shared.set('temp_hotend_tgt', statusmsg.nozzle_target_temper)
    if statusmsg.nozzle_temper is not None:
        shared.set('temp_hotend', statusmsg.nozzle_temper)

    if statusmsg.bed_target_temper is not None:
        shared.set('temp_bed_tgt', statusmsg.bed_target_temper)
    if statusmsg.bed_temper is not None:
        shared.set('temp_bed', statusmsg.bed_temper)

    if statusmsg.mc_print_stage is not None:
        shared.set('status', statusmsg.mc_print_stage)
    if statusmsg.mc_percent is not None:
        shared.set('printpct', statusmsg.mc_percent)

    print(f'Nozzle: {shared.get("temp_hotend"):.1f} / {shared.get("temp_hotend_tgt"):.1f} ' + \
          f'Bed: {shared.get("temp_bed"):.1f} / {shared.get("temp_bed_tgt"):.1f} ' + \
          f'Status: {shared.get("status")} {shared.get("printpct")} ')
    #print(statusmsg)


def bambu_connect_callback():
    print('Connecting to Bambu...')


if __name__ == '__main__':
    with open ('.vocconfig.toml', 'rb') as f:
        configdata = tomllib.load(f)

    shared = memcache.Client(['127.0.0.1:11211'], debug=0)
    shared.set('temp_hotend', 0)
    shared.set('temp_hotend_tgt', 0)
    shared.set('temp_bed', 0)
    shared.set('temp_bed_tgt', 0)
    shared.set('status', 0)
    shared.set('printpct', 0)
    try:
        print('Connecting Bambu Client')
        bambu_client = BambuClient(configdata['bambu']['hostname'],
                               configdata['bambu']['access_code'],
                               configdata['bambu']['serial'])
        bambu_client.start_watch_client(bambu_status_callback, bambu_connect_callback)

        while True:
            sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print('Closing Bambu Watch Client')
        bambu_client.stop_watch_client()

