#!/home/jrallen/adafruit/bin/python3

import argparse
import datetime
import os
import sys
import tomllib
from time import sleep

from pymemcache import serde
from pymemcache.client.base import Client

# need to have the latest version of bambu-connect from github;
# the pip version doesn't have the latest bug fixes
sys.path.append(os.path.expanduser("~/bambu-connect"))
from bambu_connect import BambuClient

STATUSMSG_DUMP = False


def callback_status(statusmsg):
    # parse statusmsg and push non-None values to cache
    statusdata = {f: statusmsg.__getattribute__(f) for f in bambu_fields}
    client_cache.set_multi({k: v for k, v in statusdata.items() if v is not None})

    # get cache data
    cachedata = client_cache.get_multi(bambu_fields)

    timestamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    print(
        " ".join(
            [
                timestamp,
                "Hotend: {nozzle_temper:.1f} ({nozzle_target_temper:.1f})",
                "Bed: {bed_temper:.1f} ({bed_target_temper:.1f})",
                "Status: {mc_print_stage} {mc_percent}",
            ]
        ).format(**cachedata)
    )
    if STATUSMSG_DUMP:
        with open("msgdump.txt", "at") as fdump:
            fdump.write("{}".format(timestamp))
            fdump.write("{}\n\n".format(statusmsg))


def callback_connect():
    print("Connecting to Printer")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--flush", action="store_true")
    args = parser.parse_args()

    with open(os.path.join(sys.path[0], "..", "config.toml"), "rb") as fconfig:
        configdata = tomllib.load(fconfig)

    bambu_fields = [
        "nozzle_temper",  # current hotend temp
        "nozzle_target_temper",  # target hotend temp
        "bed_temper",  # current bed temp
        "bed_target_temper",  # target bed temp
        "mc_print_stage",  # print status
        "mc_percent",  # print percent complete
        "layer_num",  # current layer
        "total_layer_num",  # total layers in current print
    ]

    client_cache = Client(serde=serde.pickle_serde, **configdata["memcache"])

    # initialize cache
    if args.flush:
        client_cache.flush_all()
    temp = client_cache.get_multi(bambu_fields)
    for f in bambu_fields:
        if f not in temp:
            client_cache.set(f, 0)

    # main loop
    try:
        print("Starting Bambu Client")
        client_bambu = BambuClient(**configdata["bambu"])
        client_bambu.start_watch_client(callback_status, callback_connect)

        while True:
            sleep(0.1)
    except KeyboardInterrupt:
        print("break")
    finally:
        print("Closing Bambu Client")
        client_bambu.stop_watch_client()
