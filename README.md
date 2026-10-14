Camera Server for 10€ ear camera for general purpose repurpose

I first came across a Video on Youtube (can't find it quickly, here a quick version on facebook) https://www.facebook.com/makemagazin.de/videos/ohrenschmalzentferner-als-werkzeug-f%C3%BCr-maker-johannes-hat-ein-ziemlich-ungew%C3%B6hnl/28384355824524247/ from make magazine about repurposing the ear camera for make use. I was hooked, odered two on Amazon and liked them as a tool. What I don't like is closed source chinese Apps. So I googled for opensource apps to get the videostream without the closed source app.
The upstream repo I forked this from was brilliant, worked directly with my specific camera model
(//TODO: insert amazon link).
But I want the camera to be available in my lab network without needing to connect to the wifi hotspot of the camera. So I use an Raspberry pi with a dedicated Wifi USB Stick as a camera server.
This is what this fork is about :)
And I had claude code clean up the web interface, make it responsible and collect code from different other opensource repos to enable the light and sensor data

## Credits

This fork builds on the work of others and AI assistance. Thank you!

* **[SeanPesce/Suear-Web-Viewer](https://github.com/SeanPesce/Suear-Web-Viewer)** (upstream): original MJPEG mirror, UDP command/stream protocol, device info and license parsing.
* **[alexbrickwedde/otoscope](https://github.com/alexbrickwedde/otoscope)**: `I4seasonProtocol.kt` / `FrameAssembler.kt`, reverse-engineered from the vendor's `libWifiCamera.so`. Source for the ring light command (`0x000A`, payload layout) and the packed accelerometer format in the video chunk header (bit layout, `atan2(y, z)` roll, 180° mount offset for FBPRO/R1).
* **[rbeilvert/otoscope](https://github.com/rbeilvert/otoscope)**: Wi-Fi otoscope app; Soulear/i4season support was contributed in [PR #39](https://github.com/rbeilvert/otoscope/pull/39).
* **[TJRSchmidbauer/wifi-otoscope-viewer](https://github.com/TJRSchmidbauer/wifi-otoscope-viewer)**: independent Python implementation that cross-checks the LED and accelerometer details; idea for deadband + smoothing of the rotation and documented device quirks (e.g. `0x0008` with payload powers the camera off).
* **[jduanen/EarCam](https://github.com/jduanen/EarCam)**: command table for this device family (cited via TJRSchmidbauer's README).
* **[damiencorpataux/pymjpeg](https://github.com/damiencorpataux/pymjpeg)**: reference for the HTTP MJPEG stream (via upstream).
* **[Jonathon Reinhart's ctypes struct helper](https://gist.github.com/JonathonReinhart/b6f355f13021cd8ec5d0101e0e6675b2)**: `ctypes_util.py`.

Web UI, LED/orientation endpoints and `suear_ctl.py` were written with AI assistance (Claude) and tested on real hardware.

Have fun.

# MJPEG Mirror for Suear "Smart" Ear Cleaners  
**Author: Sean Pesce**  

<p align="center">
<img align="center" title="Example clip from MJPEG stream" src="https://github.com/SeanPesce/Suear-Web-Viewer/blob/main/image/example.webp?raw=true" alt="Example clip from MJPEG stream" width="320px">
</p>  


## Overview  
A utility for converting [Suear "smart" earwax cleaner](https://play.google.com/store/apps/details?id=com.i4season.bkCamera) video streams to MJPEG for general-purpose use.  

**NOTE:** This tool has only been tested with the [LEIPUT X6](https://www.amazon.com/Ear-Wax-Removal-Remover-Android%EF%BC%88Black%EF%BC%89/dp/B09KZ8TS7L), but it should work for any product that uses `libWifiCamera.so` and/or the Suear mobile app (`com.i4season.bkCamera` - [Google Play](https://play.google.com/store/apps/details?id=com.i4season.bkCamera)/[iOS](https://apps.apple.com/us/app/suear/id1567383367)/[Direct APK download](https://web.archive.org/web/20230117012623/http://120.79.9.129/ypc/apk/Suear_V1.1.086.apk)) for video streaming in its client implementation. Relevant brands likely include:  

 * [AIDELF](https://www.amazon.com/Wireless-Endoscope-Otoscope-Waterproof-Compatible/dp/B09NLVNXQ8)
 * [BEBIRD](https://www.amazon.com/BEBIRD%C2%AE-Removal-Otoscope-Silicone-Compatible/dp/B08M9G18H3)
 * [Carenart](https://www.amazon.com/Removal-Wireless-Cleaning-Compatible-Android/dp/B09FLM4TD7)
 * [COSLUS](https://www.amazon.com/Ear-Wax-Removal-Tool-Camera/dp/B0BGP843CH)
 * [DEETOK](https://www.amazon.com/Removal-Cleaner-Camera-Otoscope-Android/dp/B0BKTMKZKJ)
 * [DJROLL](https://www.amazon.com/DJROLL-Removal-Endoscope-Wireless-Otoscope/dp/B09BC71914)
 * [Fyobyye](https://www.amazon.com/Removal-Cleaner-Camera-Otoscope-Android/dp/B0BLXM7QPT)
 * [Girug](https://www.amazon.com/Removal-Otoscope-Camera-Cleaner-Android/dp/B0BHT3KPMQ)
 * [Hasako](https://www.amazon.com/Removal-Cleaner-Camera-Candles-Android/dp/B0BKG9SNHJ)
 * [Jaydear](https://www.amazon.com/Removal-Earwax-Remover-Cleaner-Otoscope/dp/B0BBZKCZM3)
 * [Kolrry](https://www.amazon.com/Removal-Cleaner-Cleaning-Remover-Smartphones/dp/B0BDRZXH1X)
 * [LEIPUT](https://www.amazon.com/Ear-Wax-Removal-Remover-Android%EF%BC%88Black%EF%BC%89/dp/B09KZ8TS7L)
 * [Loyker](https://www.amazon.com/Removal-Cleaner-Cleaning-Otoscope-Android/dp/B0B9ZSKC99)
 * [RILIAM](https://www.amazon.com/Removal-Cleaner-Otoscope-Waterproof-Android/dp/B09NRGLGNX)
 * [ROOZADE](https://www.amazon.com/ROOZADE-Roozade-Earpick-Set-Black/dp/B0B63TYY79)
 * [SKFMA](https://www.amazon.com/earwax4ws423-Wireless-Otoscope-Endoscope-new34er4r3/dp/B09VBHG5C8)
 * [WXGTAC](https://www.amazon.com/Removal-Cleaner-Compatible-Android-Accessories/dp/B0BLBT3KP8)
 * [Xlife](https://www.amazon.com/Xlife-Removal-Remover-Blackhead-Cleaner/dp/B09QQ6X99W)
 * [Yaej](https://www.amazon.com/Cleaner-Removal-Cleaning-Otoscope-Android/dp/B09R4T1LZ3)
 * [YEOUEOZ](https://www.amazon.com/Removal-Camera-Cleaning-Compatible-Android/dp/B0B8CY2G43)


...and many, many more. Search for "Suear" on [Amazon](https://www.amazon.com/s?k=suear) for more examples.


## Web UI, ring light & orientation sensor (this fork)

Open `http://<server>:45100/` for a responsive viewer: large live image, ring light
on/off (+ brightness slider), auto-rotation from the built-in accelerometer,
calibrate/mirror/round mask, photo download, fullscreen, battery and device info.
Keyboard: `L` light, `Space` photo, `R` auto-rotation, `C` calibrate, `M` mirror, `F` fullscreen.
The page lives in `web/index.html`.

### HTTP API

| Path | Description |
| --- | --- |
| `/stream` | MJPEG stream |
| `/status` | JSON: vendor, model, firmware, serial, SSID, battery, charging, LED state |
| `/position` | JSON: latest accelerometer sample (`x/y/z` raw counts, `roll`, `slope` in degrees) |
| `/led`, `/led?on=1&brightness=100`, `/led?on=0` | Read / switch the ring light |
| `/snapshot` | Latest JPEG frame |

### Command line

```
python3 suear_ctl.py info
python3 suear_ctl.py led on        # or: led off / led on 40
python3 suear_ctl.py sensor 10     # print roll/tilt for 10 s
```

### Protocol notes

**Ring light** - command `0x000A` on UDP/10005, 3-byte payload `u8 led_id | u8 status | u8 brightness`.
`led_id` = `0x01` (camera light), OR `0x10` to write. `status` 0 = off, 1 = on (2 = blink, 3 = breathe).
Read: `01 00 00`, on: `11 01 64`, off: `11 00 00`. The reply echoes the resulting state.

**Orientation sensor** - there is no separate command: every video chunk header carries a packed
accelerometer sample in bytes 6..9 (`u32`, little endian), valid when bit0 of header byte 5 is set.
Each axis is a 9-bit magnitude plus sign bit, ~130 counts per g:
`x` = bits 20..28 / sign 29 (probe axis), `y` = bits 10..18 / sign 19, `z` = bits 0..8 / sign 9.
Roll = `atan2(y, z)`; the vendor app adds 180° for products whose id contains `FBPRO` or `R1`.

Sources: [alexbrickwedde/otoscope](https://github.com/alexbrickwedde/otoscope) (`I4seasonProtocol.kt`, reverse-engineered from `libWifiCamera.so`),
[TJRSchmidbauer/wifi-otoscope-viewer](https://github.com/TJRSchmidbauer/wifi-otoscope-viewer), [jduanen/EarCam](https://github.com/jduanen/EarCam).
Warning from those projects: command `0x0008` with a payload powers the camera off.

## Usage  

 * Power on the Suear device  
 * Connect to the Suear WiFi  
 * Start the stream mirror: `python3 suear_mirror.py --no-ssl`  

With the stream mirror running, you can view the live video in a number of ways:  

 * In a web browser; navigate to `http://127.0.0.1:45100`  
 * In VLC (GUI); go to *Media*→*Open Network Stream...*, set the URL to `http://127.0.0.1:45100/stream`, and then click *Play*  
 * In VLC (command-line); run `vlc http://127.0.0.1:45100/stream`  
 * With ffmpeg; run `ffplay -i http://127.0.0.1:45100/stream`  


## SSL/TLS    

The video stream can also be transported over TLS for security. This document won't walk you through setting up your own [PKI](https://myhomelab.gr/linux/2019/12/13/local-ca-setup.html), but the following command will generate a key pair for encrypting traffic with TLS:  

```
openssl req -new -newkey rsa:4096 -x509 -sha256 -days 365 -nodes -out cert.crt -keyout private.key
```

To start the stream mirror over HTTPS, specify the TLS key pair in the shell command:  

```
python3 suear_mirror.py cert.crt private.key
```

The HTTPS stream will then be accessible at `https://127.0.0.1:45100/stream`.  


## Contact  
If you find any bugs, please open a new [GitHub issue](https://github.com/SeanPesce/Suear-Web-Viewer/issues/new).  


## Related Projects  
 * **[Spade Web Viewer](https://github.com/SeanPesce/Spade-Web-Viewer)**, a similar project for the [Axel Glade Spade](https://www.axelglade.com/collections/e) brand of "smart" earwax cleaners.  


## Acknowledgements  
 * **[Damien Corpataux](https://github.com/damiencorpataux)**, whose [MJPEG implementation](https://github.com/damiencorpataux/pymjpeg) was used as a reference for this project.   


## License  

[GNU General Public License v2.0](LICENSE)  


---------------------------------------------

For unrelated inquiries and/or information about me, visit my **[personal website](https://SeanPesce.github.io)**.  

