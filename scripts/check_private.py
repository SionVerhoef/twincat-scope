#!/usr/bin/env python3
"""Fail if a tracked file contains a real-looking network identity.

This repository is public (see CLAUDE.md). An AMS NetId, IP address or MAC address
names one controller or device on one network, so examples, tests and templates
use the placeholders allowed below instead. Run from the repository root.
"""
import re
import subprocess
import sys

OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
# A trailing full stop ends a sentence; a full stop followed by a digit continues a number.
END = r"(?!\.?\d)"
NETID = re.compile(rf"(?<![\d.])(?:{OCTET}\.){{5}}{OCTET}{END}")
IPV4 = re.compile(rf"(?<![\d.])(?:{OCTET}\.){{3}}{OCTET}{END}")
MAC = re.compile(r"(?<![0-9A-Fa-f:-])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:-])")

# Placeholders that identify nothing. Use these in docs, tests and templates.
DOC_IP = r"(?:192\.0\.2|198\.51\.100|203\.0\.113)\.\d+"  # RFC 5737 documentation ranges
# A NetId is conventionally the IP plus .1.1, so one built from a documentation IP is fine.
NETID_OK = re.compile(rf"(?:1\.2\.3\.4|127\.0\.0\.1|0\.0\.0\.0|{DOC_IP})\.\d+\.\d+")
IPV4_OK = re.compile(
    rf"{DOC_IP}"
    r"|127\.0\.0\.1|0\.0\.0\.0|255\.\d+\.\d+\.\d+"  # loopback, any, netmasks
    r"|1\.\d+\.\d+\.\d+"  # no machine network uses 1/8; file versions such as 1.0.0.3 do
)
# "Version 1.0.0.3", <FileVersion>15.0.0.0</FileVersion>: a version number, not an address.
VERSION = re.compile(r"version", re.IGNORECASE)
MAC_OK = re.compile(
    r"00[:-]00[:-]00[:-]00[:-]00[:-]00|ff[:-]ff[:-]ff[:-]ff[:-]ff[:-]ff"
    r"|00[:-]00[:-]5e[:-]00[:-]53[:-][0-9a-f]{2}"  # RFC 7042 documentation range
    r"|01[:-]01[:-]05[:-](?:[0-9a-f]{2}[:-]){2}[0-9a-f]{2}",  # EtherCAT multicast
    re.IGNORECASE,
)

CHECKS = [("AMS NetId", NETID, NETID_OK), ("IP address", IPV4, IPV4_OK), ("MAC address", MAC, MAC_OK)]


def main():
    files = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    found = 0
    for path in filter(None, files.decode().split("\0")):
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue  # binary, submodule or deleted
        for number, line in enumerate(lines, 1):
            for label, pattern, allowed in CHECKS:
                for match in pattern.finditer(line):
                    if allowed.fullmatch(match.group()) or VERSION.search(line, 0, match.start()):
                        continue
                    print(f"{path}:{number}: {label} {match.group()}")
                    found += 1
    if found:
        print(f"\n{found} real-looking identifier(s). Replace them with a placeholder "
              "(see scripts/check_private.py) and read CLAUDE.md.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
