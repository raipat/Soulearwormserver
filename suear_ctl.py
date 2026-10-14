#!/usr/bin/env python3
"""
Small command line tool to talk to a Suear/Soulear camera directly
(connect to the camera's WiFi first).

    python3 suear_ctl.py info             # device info, battery, LED state
    python3 suear_ctl.py led on [0-100]   # ring light on (optional brightness)
    python3 suear_ctl.py led off
    python3 suear_ctl.py led              # read LED state
    python3 suear_ctl.py sensor [seconds] # print accelerometer roll/tilt live
"""
import sys
import time

import suear_mirror


def main(argv):
    if len(argv) < 2 or argv[1] in ('-h', '--help'):
        print(__doc__)
        return 1
    client = suear_mirror.SuearClient()
    cmd = argv[1]

    if cmd == 'info':
        for k, v in client.status().items():
            print(f'{k:>10}: {v}')

    elif cmd == 'led':
        if len(argv) < 3:
            print(client.led())
        else:
            on = argv[2].lower() in ('on', '1', 'an')
            brightness = int(argv[3]) if len(argv) > 3 else None
            print(client.led(on, brightness))

    elif cmd == 'sensor':
        duration = float(argv[2]) if len(argv) > 2 else 10.0
        client.connect()
        client.device_info()  # needed for the mount offset
        client.open_video()   # accelerometer samples only arrive with video chunks
        end = time.time() + duration
        last_print = 0
        try:
            while time.time() < end:
                client.get_frame()
                if client.accel is not None and time.time() - last_print > 0.1:
                    p = client.position()
                    roll = '   n/a' if p['roll'] is None else f"{p['roll']:6.1f}"
                    print(f"roll {roll} deg   tilt {p['slope']:6.1f} deg   "
                          f"x/y/z {p['x']:4d} {p['y']:4d} {p['z']:4d}   raw {p['raw']:#010x}")
                    last_print = time.time()
        finally:
            client.disconnect()
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
