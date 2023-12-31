# based on https://stackoverflow.com/questions/8110310/simple-way-to-query-connected-usb-devices-info-in-python

import re
import subprocess
import sys

DEVICES = ["0fd9:0090"]

device_re = re.compile(
    b"Bus\s+(?P<bus>\d+)\s+Device\s+(?P<device>\d+).+ID\s(?P<id>\w+:\w+)\s(?P<tag>.+)$",
    re.I,
)
df = subprocess.check_output("lsusb")
devices = []
for i in df.split(b"\n"):
    if i:
        info = device_re.match(i)
        if info:
            dinfo = info.groupdict()
            dinfo["device"] = "/dev/bus/usb/%s/%s" % (
                dinfo.pop("bus"),
                dinfo.pop("device"),
            )
            devices.append(dinfo)

result = 1
for device in devices:
    if device["id"].decode() in DEVICES:
        result = 0

sys.exit(result)
