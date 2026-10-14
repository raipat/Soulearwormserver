#!/usr/bin/env python3
# Author: Sean Pesce

# The following project was used as a reference implementation for the HTTP-based MPJEG stream:
# https://github.com/damiencorpataux/pymjpeg

# Use the following shell command to create a self-signed TLS certificate and private key:
#    openssl req -new -newkey rsa:4096 -x509 -sha256 -days 365 -nodes -out cert.crt -keyout private.key


import html
import http.server
import json
import os
import queue
import threading
import urllib.parse
import select
import socket
import ssl
import sys
import time

from io import BytesIO

import suear_struct
from suear_util import ping, accel_xyz, roll_degrees, slope_degrees, mount_offset_degrees


UI_HTML_FPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web', 'index.html')


class HttpHandler(http.server.BaseHTTPRequestHandler):
    BOUNDARY = b'--SP-LaputanMachine--'
    SUEAR_CLIENT = None
    RENDER_RATE = 0  # One frame is rendered locally (with MatPlotLib) for every RENDER_RATE frames sent to the HTTP client (Set to <1 to never render locally)
    PROTOCOL = 'http'
    PORT = 45100
    
    
    @classmethod
    def HEADERS_BASE(cls):
        headers = {
            'Cache-Control': 'no-store, no-cache, must-revalidate, pre-check=0, post-check=0, max-age=0',
            'Content-Type': f'multipart/x-mixed-replace;boundary={cls.BOUNDARY.decode("ascii")}',
            #'Connection': 'close',
            'Pragma': 'no-cache',
            'Access-Control-Allow-Origin': '*',  # CORS
        }
        return headers
    
    
    @classmethod
    def HEADERS_IMAGE(cls, length):
        headers = {
            'X-Timestamp': time.time(),
            'Content-Length': str(int(length)),
            'Content-Type': 'image/jpeg',
        }
        return headers
    
    
    def send_json(self, obj, status=200):
        data = json.dumps(obj).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(data)


    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(url.query)
        self.path = url.path
        suear_client = self.__class__.SUEAR_CLIENT

        if self.path in ('/', '/index.html'):
            try:
                with open(UI_HTML_FPATH, 'rb') as f:
                    data = f.read()
            except OSError:
                self.send_response(500)
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(f'UI file missing: {UI_HTML_FPATH}'.encode('utf-8'))
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(data)
            return

        if self.path in ('/status', '/position', '/led', '/snapshot'):
            if suear_client is None:
                self.send_json({'error': 'Suear client unavailable'}, 503)
                return
            try:
                if self.path == '/status':
                    self.send_json(suear_client.status())
                elif self.path == '/position':
                    self.send_json(suear_client.position())
                elif self.path == '/led':
                    on = query.get('on', [None])[0]
                    brightness = query.get('brightness', [None])[0]
                    if on is None:
                        state = suear_client.led()
                    else:
                        state = suear_client.led(on not in ('0', 'false', 'off'),
                                                 None if brightness is None else int(brightness))
                    self.send_json(state)
                elif self.path == '/snapshot':
                    jpeg = suear_client.last_jpeg
                    if jpeg is None:
                        self.send_json({'error': 'no frame received yet'}, 404)
                        return
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Disposition',
                                     f'inline; filename="suear_{time.strftime("%Y%m%d_%H%M%S")}.jpg"')
                    self.send_header('Content-Length', str(len(jpeg)))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.wfile.write(jpeg)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                print(f'[ERROR] {self.path}: {type(e).__name__}: {e}')
                try:
                    self.send_json({'error': f'{type(e).__name__}: {e}'}, 502)
                except Exception:
                    pass
            return

        if self.path not in ('/stream', '/battery', '/model', '/vendor', '/version', '/ssid', '/capacity', '/charging', '/serial'):
            self.send_response(404)
            self.send_header('Connection', 'close')
            self.end_headers()
            return
        
        if suear_client is None:
            self.send_response(503)  # Service Unavailable
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(b'Error: Suear client unavailable')
            return
            
        
        self.send_response(200)
        self.send_header('X-Battery', str(suear_client.battery_level))
        #self.send_header('X-Charging', str(int(suear_client.is_charging)))
        self.send_header('Connection', 'close')
        
        if self.path == '/battery':
            data = html.escape(str(suear_client.battery_level)).encode('ascii')
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
            return
        
        elif self.path == '/model':
            data = html.escape(str(suear_client.model)).encode('ascii')
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
            return
        
        elif self.path == '/serial':
            data = html.escape(str(suear_client.serial_num)).encode('ascii')
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
            return
        
        elif self.path == '/vendor':
            data = html.escape(str(suear_client.vendor)).encode('ascii')
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
            return
        
        elif self.path == '/version':
            data = html.escape(str(suear_client.version)).encode('ascii')
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
            return
        
        elif self.path == '/ssid':
            data = html.escape(str(suear_client.ssid)).encode('ascii')
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
            return
        
        elif self.path == '/capacity':
            data = html.escape(str(suear_client.capacity)).encode('ascii')
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
            return
        
        elif self.path == '/charging':
            data = html.escape(str(int(suear_client.is_charging))).encode('ascii')
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
            return
        
        elif self.path == '/stream':
            for k, v in self.__class__.HEADERS_BASE().items():
                self.send_header(k, v)
            suear_client.connect()

            resp = suear_client.open_video()

            while suear_client.streaming:
                frame = suear_client.get_frame()
                if frame is None:
                    continue
                
                self.end_headers()
                self.wfile.write(self.__class__.BOUNDARY)
                self.end_headers()
                img_headers = self.__class__.HEADERS_IMAGE(len(frame.data))
                for k, v in img_headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(frame.data)
                suear_client.last_jpeg = bytes(frame.data)
                if self.__class__.RENDER_RATE > 0 and frame.index % self.__class__.RENDER_RATE == 0:
                    frame.render()
                
                #print(f'Reconstructed frame: {frame.index}')
                #time.sleep(0.016)  # ~60FPS
            
            suear_client.streaming = False
            for sock in suear_client.stream_socks:
                if not sock._closed:
                    sock.close()
            suear_client.stream_socks = []
        return


class JpgFrame:
    BUF_SZ = 131072
    
    def __init__(self, index=None, width=None, height=None, first_chunk_idx=None, coords=None):
        self._buf = bytearray(self.__class__.BUF_SZ)
        if None not in (index, width, height, first_chunk_idx):
            self.init(index, width, height, first_chunk_idx, coords)
        return
    
    
    def init(self, index, width, height, first_chunk_idx, coords=None):
        self.index = int(index)
        self.width = int(width)
        self.height = int(height)
        self.first_chunk_idx = first_chunk_idx
        self.x = None
        self.y = None
        self.z = None
        if coords is not None and type(coords) == tuple and len(coords) == 3:
            self.x = int(coords[0])
            self.y = int(coords[1])
            self.z = int(coords[2])
        self.total = None
        self.complete = False  # True when all chunks have been acquired
        self.chunk_sz = None   # All but the final chunk have the same size
        self.acquired_sz = 0   # Total number of bytes acquired
        self._data = memoryview(self._buf)
    
    
    def add_chunk(self, idx, data, final=0):
        assert not self.complete, 'Attempt to add a chunk to a completed frame'
        if not final:
            if self.chunk_sz is not None:
                assert self.chunk_sz == len(data), f'Chunk size mismatch:  {self.chunk_sz=}  {len(data)=}'
            self.chunk_sz = len(data)
        elif self.chunk_sz is None:
            # Received last chunk before any other chunk... just allow the bad data?
            self.chunk_sz = len(data)
        
        # Chunk index is only 8 bits; 255 rolls over to 0, so we correct this:
        if idx < self.first_chunk_idx:
            idx += 256

        start = self.chunk_sz * (idx - self.first_chunk_idx)
        self._data[start:start+len(data)] = data
        self.acquired_sz += len(data)
        if final:
            self.total = int(final)
        if self.total and self.acquired_sz > self.chunk_sz * (self.total-1):
            self.complete = True
        return
    
    
    @property
    def data(self):
        assert self.complete, 'Attempt to reassemble incomplete frame'
        return self._data[:self.acquired_sz]
    
    
    @property
    def position(self):
        coords = (self.x, self.y, self.z)
        if None not in coords:
            return coords
        return None
    
    
    def render(self, title=None):
        import matplotlib.pyplot
        img = matplotlib.pyplot.imread(BytesIO(self.data), format='jpeg')
        if title is None:
            title = f'Frame {self.index}'
        matplotlib.pyplot.title(title)
        matplotlib.pyplot.imshow(img)
        matplotlib.pyplot.show(block=False)
        matplotlib.pyplot.pause(0.001)



class SuearClient:
    DEFAULT_SERVER = '192.168.1.1'
    COMMAND_PORT = 10005  # UDP
    STREAM_INIT_PORT = 10006  # UDP
    # Which local port the device pushes video chunks to is apparently
    # hardcoded per firmware build, not negotiated in the protocol - some
    # X6-family units use 22785, others 22789 (see issue #9). Rather than
    # guess, listen on all known ports and use whichever one actually
    # receives data.
    STREAM_RECV_PORTS = (22785, 22789)
    FRAME_CHUNK_SZ = 1456
    UDP_READ_SZ = 8192
    FRAME_QUEUE_MAX = 8
    CMD_TIMEOUT_S = 0.5
    CMD_ATTEMPTS = 4
    LED_CAMERA = 0x01   # LED id of the camera ring light
    LED_WRITE = 0x10    # OR-ed into the LED id to write instead of read
    # If no stream data arrives for this many seconds, get_frame()
    # automatically disconnects and reconnects instead of hanging forever
    # (the original blocking recv_into() had no timeout at all, so any
    # pause in the device's output - a Wi-Fi hiccup, a brief stall - would
    # block indefinitely with no way to recover short of restarting the
    # script).
    STALL_RECONNECT_AFTER_S = 8.0
    SELECT_TIMEOUT_S = 1.0
    
    def __init__(self, server=DEFAULT_SERVER, cmd_send_index=0):
        self.server = socket.gethostbyname(server)  # Server host name or IP address
        self.cmd_send_index = int(cmd_send_index) & 0xffff  # Incremented with each message sent to the server (2 bytes)
        self._license = None
        self._camera_config = None
        self._device_info = None
        self._connected = False
        self.command_sock = None
        self.stream_socks = []
        self._last_recv_at = 0.0
        # Request/reply pairs on the command socket are serialised: the HTTP
        # server is threaded, so battery polling, LED control and the stream
        # handler could otherwise steal each other's UDP replies.
        self._cmd_lock = threading.RLock()
        self.last_jpeg = None
        # Latest accelerometer sample from the video chunk headers
        self.accel = None
        self.accel_at = 0.0
        self.stream_buf = memoryview(bytearray(self.__class__.UDP_READ_SZ))
        self.streaming = False
        self.frame_queue = queue.Queue()
        self.frame_dict = {}
        self.frame_reserve = []
        self.frame_reserve_idx = 0
        for i in range(self.__class__.FRAME_QUEUE_MAX):
            self.frame_reserve.append(JpgFrame())
        return
    
    
    def connect(self):
        if self._connected and self.command_sock is not None:
            return
        print(f'Connecting to {self.server}')
        if not ping(self.server):
            raise IOError(f'[ERROR] No ICMP response from {self.server}')
        self.command_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        self._connected = True
    
    
    def disconnect(self):
        self.streaming = False
        if self.command_sock is not None:
            if not self.command_sock._closed:
                self.command_sock.close()
            self.command_sock = None
        for sock in self.stream_socks:
            if not sock._closed:
                sock.close()
        self.stream_socks = []
        self._connected = False
    
    
    def stream_to_matplotlib(self):
        # Don't use this function
        self.connect()
        self.streaming = True
        self.stream_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_address = (self.server, self.__class__.STREAM_INIT_PORT)
        data = self.__class__.READ_STREAM_REQUEST
        sent = self.stream_sock.sendto(data, server_address)
        assert sent == len(data), f'UDP message was {len(data)} bytes but only {sent} were sent'
        while self.streaming:
            frame = self.get_frame()
            if frame is None:
                continue
            
            frame.render()
            #print(f'Reconstructed frame: {frame.index}')
            #time.sleep(0.016)  # ~60FPS
        
        self.streaming = False
        if self.stream_sock is not None and not self.stream_sock._closed:
            # @TODO: Send EndStream message
            self.stream_sock.close()
        self.stream_sock = None
        return


    def get_frame(self):
        if not self.streaming:
            return None

        frame = None

        while self.stream_socks and self.streaming:
            ready, _, _ = select.select(self.stream_socks, [], [], self.__class__.SELECT_TIMEOUT_S)

            if not ready:
                # No data on any stream socket within the select window.
                # Only treat this as a real problem if it's persisted past
                # the stall threshold - a single empty select() is normal.
                if time.time() - self._last_recv_at > self.__class__.STALL_RECONNECT_AFTER_S:
                    print(f'[WARN] No stream data for over {self.__class__.STALL_RECONNECT_AFTER_S}s - reconnecting')
                    try:
                        self.disconnect()
                        self.connect()
                        self.open_video()
                    except Exception as e:
                        print(f'[ERROR] Reconnect attempt failed: {e}')
                        time.sleep(1)
                    return None
                continue

            for sock in ready:
                nread = sock.recv_into(self.stream_buf)
                self._last_recv_at = time.time()
                buf = self.stream_buf[:nread]
                offs = 0

                # Parse response for multiple messages
                while True:
                    read_sz = suear_struct.SuearUdpMsg_StreamChunk.sizeof()
                    data = buf[offs:offs+read_sz]
                    offs += read_sz

                    if len(data) < read_sz:
                        if len(data) > 0:
                            print(f'len(data) < suear_struct.SuearUdpMsg_StreamChunk.sizeof()')
                            print(data)
                        break

                    msg = suear_struct.SuearUdpMsg_StreamChunk.from_bytes(data)
                    if msg.has_accel:
                        self.accel = int(msg.accel)
                        self.accel_at = time.time()
                    read_sz = self.__class__.FRAME_CHUNK_SZ
                    data = buf[offs:offs+read_sz]
                    offs += len(data)

                    if msg.n_frame in self.frame_dict:
                        parse_frame = self.frame_dict[msg.n_frame]
                    else:
                        while len(self.frame_dict) >= len(self.frame_reserve):
                            # Discard unfinished frames if no free frame slots are available
                            print('Discarding frame')
                            self.frame_dict.pop(self.frame_queue.get().index, None)
                        parse_frame = self.frame_reserve[self.frame_reserve_idx]
                        self.frame_reserve_idx += 1
                        if self.frame_reserve_idx >= len(self.frame_reserve):
                            self.frame_reserve_idx = 0
                        parse_frame.init(msg.n_frame, msg.res_width, msg.res_height, msg.n_chunk)
                        self.frame_dict[msg.n_frame] = parse_frame
                        self.frame_queue.put(parse_frame)

                    parse_frame.add_chunk(msg.n_chunk, data, msg.total_chunks)

                    # If a frame enters the "complete" state, pop frames from the queue (and delete them from
                    # the dict) until the popped frame is the completed frame
                    if parse_frame.complete:
                        while True:
                            tmp_frame = self.frame_queue.get()
                            self.frame_dict.pop(tmp_frame.index, None)
                            if parse_frame.index == tmp_frame.index:
                                break
                        frame = parse_frame
                        return frame

        return frame
    
    
    def mirror_http(self, cert_fpath=None, privkey_fpath=None):
        port = 45100
        HttpHandler.SUEAR_CLIENT = self
        HttpHandler.PORT = port
        server_address = ('0.0.0.0', port)
        httpd = http.server.ThreadingHTTPServer(server_address, HttpHandler)
        if None not in (cert_fpath, privkey_fpath):
            HttpHandler.PROTOCOL = 'https'
            context = ssl.SSLContext(ssl.PROTOCOL_TLS)
            context.load_cert_chain(certfile=cert_fpath, keyfile=privkey_fpath, password='')
            httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        print(f'Serving {HttpHandler.PROTOCOL.upper()} on {HttpHandler.PROTOCOL.lower()}://{server_address[0]}:{server_address[1]}')
        httpd.serve_forever()
    
    
    @property
    def connected(self):
        return self._connected
    
    
    def increment(self):
        """
        Increment and return the command-send-index while restricting it to two bytes
        """
        self.cmd_send_index = int(self.cmd_send_index + 1) & 0xffff
        return self.cmd_send_index

    
    def send_command(self, msg, connecting=False, port=None, sock=None):
        if type(msg) not in (bytes, suear_struct.SuearUdpMsg_0xffeeffee,):
            raise TypeError(f'Bad request message type: {type(msg)}')
        
        if type(msg) == bytes:
            data = b''
            if msg.startswith(b'\xee\xff\xee\xff'):
                data = msg[suear_struct.SuearUdpMsg_0xffeeffee.sizeof():]
                msg = suear_struct.SuearUdpMsg_0xffeeffee.from_bytes(msg)
            else:
                raise ValueError(f'Invalid UDP message magic bytes: {msg[:100]}')
            
            msg.data = data
            msg.length = len(data)
        
        if not (connecting or self.connected):
            self.connect()
        
        msg.id = self.increment()
        if not port:
            port = self.__class__.COMMAND_PORT
        if not sock:
            sock = self.command_sock
        #print(f'\n[Client -> {self.server}:{port}]\n{msg.type_name} {msg}\n{msg.data}\n')
        
        server_address = (self.server, port)
        with self._cmd_lock:
            sock.settimeout(self.__class__.CMD_TIMEOUT_S)
            response_data = None
            for attempt in range(self.__class__.CMD_ATTEMPTS):
                sock.sendto(bytes(msg), server_address)
                try:
                    while True:
                        response_data, server = sock.recvfrom(0x1000)
                        if server[0] != self.server or len(response_data) < msg.__class__.sizeof():
                            continue
                        # Skip late replies to earlier requests of a different type
                        if int.from_bytes(response_data[6:8], 'little') != msg.type:
                            continue
                        break
                    break
                except socket.timeout:
                    response_data = None
            if response_data is None:
                raise TimeoutError(f'No reply from {self.server}:{port} for command {msg.type:#06x}')
        response = msg.__class__.from_bytes(response_data[:msg.__class__.sizeof()])
        response_data = response_data[msg.__class__.sizeof():]
        if response.length > 0:
            # response.data, server = sock.recvfrom(response.length)
            # assert server[0] == self.server, f'Response from unknown host {server[0]}'
            response.data = response_data
            response_data = response_data[response.length:]
        assert len(response_data) == 0, f'Encountered extraneous UDP message data: {response_data}'
        #print(f'[{self.server}:{port} -> Client]\n{response.type_name} {response}\n{response.data}\n\n')
        return response
    

    def open_video(self):
        """
        When this is called, the device starts sending JPEG frames to the client
        """
        if self.streaming:
            return

        stream_init_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        msg = b'\xee\xff\xee\xff\x00\x00\x04\x00\x01\x00\x00\x00'
        response = self.send_command(msg, port=self.__class__.STREAM_INIT_PORT, sock=stream_init_sock)
        assert response.err_code == 0, f'UDP message error code {response.err_code}'
        stream_init_sock.close()

        self.stream_socks = []
        for port in self.__class__.STREAM_RECV_PORTS:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(('0.0.0.0', port))
            self.stream_socks.append(sock)

        self._last_recv_at = time.time()
        self.streaming = True

        return response


    @property
    def license(self):
        if not self._license:
            msg = b'\xee\xff\xee\xff\x00\x00\x02\x00\x01\x00\x00\x00'
            response = self.send_command(msg)
            self._license = suear_struct.SuearLicenseInfo.from_bytes(response.data)
        return self._license


    @property
    def camera_config(self):
        if not self._camera_config:
            msg = b'\xee\xff\xee\xff\x00\x00\x0c\x00\x01\x00\x00\x00'
            response = self.send_command(msg)
            self._camera_config = response.data
        return self._camera_config


    def device_info(self, update=True):
        if (not self._device_info) or update:
            msg = b'\xee\xff\xee\xff\x00\x00\x01\x00\x01\x00\x00\x00'
            response = self.send_command(msg)
            self._device_info = suear_struct.SuearDeviceInfo.from_bytes(response.data)
        return self._device_info


    @property
    def battery_level(self):
        return int(self.device_info(update=True).battery)


    @property
    def is_charging(self):
        return self.device_info(update=True).is_charging
    
    
    @property
    def vendor(self):
        return self.device_info(update=False).vendor


    @property
    def model(self):
        return self.device_info(update=False).product_id


    @property
    def version(self):
        return self.device_info(update=False).fw_version


    @property
    def ssid(self):
        return self.device_info(update=False).ssid
    

    @property
    def serial_num(self):
        return self.license.serial_num


    @property
    def capacity(self):
        return self.device_info(update=False).capacity


    def led(self, on=None, brightness=None):
        """
        Ring light control, command 0x000A on UDP/10005.

        Payload (request and reply): u8 led_id | u8 status | u8 brightness
          led_id:     0x01 = camera ring light; OR 0x10 to write instead of read
          status:     0 = off, 1 = on (2 = blink, 3 = breathe also exist)
          brightness: 0..100 (the vendor app only ever writes 100 or 0; many
                      units don't actually dim)
        The reply carries the resulting state in the same layout.

        Call without arguments to read the current state.
        Sources: alexbrickwedde/otoscope (I4seasonProtocol.kt), jduanen/EarCam
        """
        if on is None:
            payload = bytes([self.__class__.LED_CAMERA, 0, 0])
        else:
            if brightness is None:
                brightness = 100 if on else 0
            brightness = max(0, min(100, int(brightness)))
            payload = bytes([self.__class__.LED_WRITE | self.__class__.LED_CAMERA, 1 if on else 0, brightness])
        msg = b'\xee\xff\xee\xff\x00\x00\x0a\x00\x01\x00\x00\x00' + payload
        response = self.send_command(msg)
        data = bytes(response.data)
        if response.err_code != 0 or len(data) < 3:
            raise IOError(f'LED command rejected: err={response.err_code}, data={data!r}')
        return {'on': bool(data[1]), 'mode': int(data[1]), 'brightness': int(data[2])}


    def position(self):
        """Latest accelerometer sample decoded to roll/tilt (None until video is streaming)"""
        if self.accel is None:
            return {'available': False}
        x, y, z = accel_xyz(self.accel)
        roll = roll_degrees(self.accel)
        offset = mount_offset_degrees(self.device_info(update=False).product_id) if self._device_info else 0.0
        return {
            'available': True,
            'raw': self.accel,
            'x': x, 'y': y, 'z': z,
            'roll': None if roll is None else (roll + offset) % 360.0,
            'roll_raw': roll,
            'slope': slope_degrees(self.accel),
            'mount_offset': offset,
            'age_ms': int((time.time() - self.accel_at) * 1000),
        }


    def status(self):
        info = self.device_info(update=True)
        try:
            led = self.led()
        except Exception:
            led = None
        return {
            'vendor': info.vendor,
            'model': info.product_id,
            'version': info.fw_version,
            'ssid': info.ssid,
            'serial': self.serial_num,
            'battery': int(info.battery),
            'charging': bool(info.is_charging),
            'led': led,
            'streaming': self.streaming,
        }
        
        
        
if __name__ == '__main__':
    no_ssl_flag = '--no-ssl'
    if len(sys.argv) < 2 or (len(sys.argv) < 3 and no_ssl_flag not in sys.argv):
        print(f'\nUsage:\n\t{sys.argv[0]} {no_ssl_flag}\n\t{sys.argv[0]} <PEM certificate file> <private key file>\n')
        sys.exit()

    cert_fpath = None
    privkey_fpath = None
    if no_ssl_flag not in sys.argv:
        cert_fpath = sys.argv[1]
        privkey_fpath = sys.argv[2]

    client = SuearClient()
    print(f'Device: {client.vendor} {client.model} {client.version}  (Serial number: {client.serial_num})')
    print(f'Battery: {client.battery_level}% ({"C" if client.is_charging else "Not c"}harging)')
    
    client.mirror_http(cert_fpath, privkey_fpath)
