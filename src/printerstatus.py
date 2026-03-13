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


def bambu_status_callback(statusmsg):
    status_data = {f: statusmsg.__getattribute__(f) for f in bambu_fields}
    sharedcache.set_multi({k: v for k, v in status_data.items() if v is not None})

    cache_data = sharedcache.get_multi(bambu_fields)

    print(
        " ".join(
            [
                datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "Nozzle: {nozzle_temper:.1f} ({nozzle_target_temper:.1f})",
                "Bed: {bed_temper:.1f} ({bed_target_temper:.1f})",
                "Status: {mc_print_stage} {mc_percent}",
            ]
        ).format(**cache_data)
    )
    # with open('msgdump.txt', 'at') as ftemp:
    #    ftemp.write('{}\n\n'.format(statusmsg))


def bambu_connect_callback():
    print("Connecting to Printer")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--flush", action="store_true")
    args = parser.parse_args()

    with open(os.path.join(sys.path[0], "..", "config.toml"), "rb") as f:
        configdata = tomllib.load(f)

    bambu_fields = [
        "nozzle_target_temper",
        "nozzle_temper",
        "bed_target_temper",
        "bed_temper",
        "mc_print_stage",
        "mc_percent",
    ]
    sharedcache = Client(serde=serde.pickle_serde, **configdata["memcache"])
    if args.flush:
        sharedcache.flush_all()
    _ = sharedcache.get_multi(bambu_fields)
    for f in bambu_fields:
        if f not in _:
            shared.set(f, 0)

    try:
        print("Starting Bambu Client")
        bambu_client = BambuClient(**configdata["bambu"])
        bambu_client.start_watch_client(bambu_status_callback, bambu_connect_callback)

        while True:
            sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        print("Closing Bambu Client")
        bambu_client.stop_watch_client()
