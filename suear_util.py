#!/usr/bin/env python3
# Author: Sean Pesce

import os
import platform
import socket
import sys


def ping(host, timeout=1):
    """
    Returns True if the target host sent an ICMP response within the specified timeout interval
    """
    # Protect against command injection
    if type(host) != str:
        raise TypeError(f'Non-string type for "host" argument: {type(host)}')
    # Alphabet for IP addresses and host names
    safe_alphabet = '.:0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_'
    for c in host:
        if c not in safe_alphabet:
            raise ValueError(f'Invalid character in "host" argument: "{c}"')
    host = socket.gethostbyname(host)
    # Determine argument syntax (Linux vs Windows)
    count_flag = 'c'
    dev_null = '/dev/null'
    quote_char = '\''
    wait_flag = 'w'
    if 'windows' in platform.system().lower():
        count_flag = 'n'
        dev_null = 'NUL'
        quote_char = '"'
    if 'darwin' in platform.system().lower():
        wait_flag = 'W'

    cmd = f'ping -{count_flag} 1 -{wait_flag} {int(timeout)} {quote_char}{host}{quote_char} 2>&1 > {dev_null}'
    retcode = os.system(cmd)
    return retcode == 0


# ---------------------------------------------------------------------------
# Accelerometer ("G-sensor") decoding
#
# Every video chunk header carries a packed 32-bit accelerometer sample
# (bytes 6..9, valid when header flag bit0 is set). Each axis is a 9-bit
# magnitude plus a separate sign bit, roughly 130 counts per g:
#
#     x = bits 20..28, sign bit 29   (along the probe's long axis)
#     y = bits 10..18, sign bit 19
#     z = bits  0..8,  sign bit  9
#
# The vendor app computes atan(y/z) and fixes the quadrant from the sign bits,
# i.e. roll = atan2(y, z), and adds a fixed 180 deg for products whose sensor
# is mounted upside down (product id containing "FBPRO" or "R1").
# Sources: alexbrickwedde/otoscope (I4seasonProtocol.kt),
#          TJRSchmidbauer/wifi-otoscope-viewer (suear_util.py)
# ---------------------------------------------------------------------------

import math

ACCEL_COUNTS_PER_G = 130.0


def accel_axis(packed, shift, sign_bit):
    magnitude = (int(packed) >> shift) & 0x1ff
    return -magnitude if (int(packed) >> sign_bit) & 1 else magnitude


def accel_xyz(packed):
    """Raw (x, y, z) accelerometer counts from the packed sample"""
    return (accel_axis(packed, 20, 29), accel_axis(packed, 10, 19), accel_axis(packed, 0, 9))


def roll_degrees(packed):
    """
    Roll of the probe around its long axis in degrees [0, 360), or None when the
    probe points straight up/down and roll is undefined.
    """
    _, y, z = accel_xyz(packed)
    if y == 0 and z == 0:
        return None
    return math.degrees(math.atan2(y, z)) % 360.0


def slope_degrees(packed):
    """Tilt of the probe's long axis against the horizontal, in degrees (-90..90)"""
    x, y, z = accel_xyz(packed)
    return math.degrees(math.atan2(x, math.hypot(y, z)))


def mount_offset_degrees(product):
    """Fixed sensor-mount correction the vendor app applies for some products"""
    product = (product or '').upper()
    return 180.0 if ('FBPRO' in product or 'R1' in product) else 0.0
