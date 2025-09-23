#!/usr/bin/env python3
import cv2
import io
import time
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from PIL import Image
import os
import signal
from datetime import datetime
import pytz

try:
    from gpiozero import LED, Servo
    GPIO_PIN_ONOFF = 6
    GPIO_PIN_BLINK = 26
    GPIO_PAN = 17 # GPIO pin for Pan (left/right) servo
    GPIO_TILT = 18 # GPIO pin for Tilt (up/down) servo
    GPIO_LASER = 27 # GPIO pin for laser
    
    gpio_led_onoff = LED(GPIO_PIN_ONOFF)
    gpio_led_blink = LED(GPIO_PIN_BLINK)
    pan_servo = Servo(GPIO_PAN)
    tilt_servo = Servo(GPIO_TILT)
    laser = LED(GPIO_LASER)
    print(f"GPIO pins {GPIO_PIN_ONOFF}, {GPIO_PIN_BLINK}, {GPIO_PAN}, {GPIO_TILT}, and {GPIO_LASER} initialized.")
    GPIO_SUPPORT = True
except ImportError:
    print("Warning: gpiozero library not found. GPIO control will be disabled.")
    print("Please install it with: sudo apt update && sudo apt install python3-gpiozero")
    GPIO_SUPPORT = False

# Configuration
PORT = 8080
RESOLUTION = (640, 480)
FRAMERATE = 24
JPEG_QUALITY = 80
CAMERA_INDEX = 0

# Set Thailand timezone
THAILAND_TIMEZONE = pytz.timezone('Asia/Bangkok')

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()
    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

output = StreamingOutput()

# Global variables for control threads
blink_stop_event = threading.Event()
current_blink_thread = None
# Global variable for latency
last_frame_latency = 0

def blink_led(count):
    if not GPIO_SUPPORT:
        return
    for i in range(count):
        if blink_stop_event.is_set():
            break
        gpio_led_blink.on()
        time.sleep(0.5)
        gpio_led_blink.off()
        time.sleep(0.5)
    print("Blink sequence finished or stopped.")
    blink_stop_event.clear()

class MouseControlThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.x = 0
        self.y = 0
        self.running = True
        self.lock = threading.Lock()
    
    def set_pos(self, x, y):
        with self.lock:
            self.x = x
            self.y = y

    def run(self):
        if not GPIO_SUPPORT:
            return

        current_pan_angle = 0
        current_tilt_angle = 0
        
        PAN_RANGE = 90
        TILT_RANGE = 45
        
        VIDEO_WIDTH = RESOLUTION[0]
        VIDEO_HEIGHT = RESOLUTION[1]
        
        HALF_VIDEO_WIDTH = VIDEO_WIDTH / 2
        HALF_VIDEO_HEIGHT = VIDEO_HEIGHT / 2

        while self.running:
            with self.lock:
                target_x = self.x
                target_y = self.y
            
            target_pan_angle = (target_x / HALF_VIDEO_WIDTH) * PAN_RANGE
            target_tilt_angle = (target_y / HALF_VIDEO_HEIGHT) * TILT_RANGE
            
            target_pan_angle = max(-PAN_RANGE, min(PAN_RANGE, target_pan_angle))
            target_tilt_angle = max(-TILT_RANGE, min(TILT_RANGE, target_tilt_angle))

            if abs(target_pan_angle - current_pan_angle) > 1:
                current_pan_angle += (target_pan_angle - current_pan_angle) * 0.1
                pan_servo.value = current_pan_angle / 90.0
            
            if abs(target_tilt_angle - current_tilt_angle) > 1:
                current_tilt_angle += (target_tilt_angle - current_tilt_angle) * 0.1
                tilt_servo.value = current_tilt_angle / 90.0

            time.sleep(0.01)

    def stop(self):
        self.running = False
        self.join()

mouse_control_thread = MouseControlThread()
if GPIO_SUPPORT:
    mouse_control_thread.start()

class StreamingHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        global current_blink_thread, blink_stop_event
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            try:
                with open('index.html', 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.send_header('Content-Length', len(content))
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, 'File Not Found: %s' % self.path)
        elif self.path.endswith('.mp3'):
            try:
                # This handles the audio file request
                with open(self.path[1:], 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'audio/mpeg')
                self.send_header('Content-Length', len(content))
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, 'File Not Found: %s' % self.path)
        elif self.path == '/gpio_on':
            if GPIO_SUPPORT:
                try:
                    gpio_led_onoff.on()
                    print(f"GPIO pin {GPIO_PIN_ONOFF} turned ON")
                    self.send_response(200)
                    self.end_headers()
                except Exception as e:
                    self.send_error(500, f"Error controlling GPIO: {e}")
            else:
                self.send_error(503, "GPIO control is not available")
        elif self.path == '/gpio_off':
            if GPIO_SUPPORT:
                try:
                    gpio_led_onoff.off()
                    print(f"GPIO pin {GPIO_PIN_ONOFF} turned OFF")
                    self.send_response(200)
                    self.end_headers()
                except Exception as e:
                    self.send_error(500, f"Error controlling GPIO: {e}")
            else:
                self.send_error(503, "GPIO control is not available")
        elif self.path.startswith('/gpio_blink'):
            if GPIO_SUPPORT:
                try:
                    query = self.path.split('?')[-1]
                    count_str = query.split('=')[-1]
                    count = int(count_str)
                    if current_blink_thread and current_blink_thread.is_alive():
                        print("Stopping previous blink thread...")
                        blink_stop_event.set()
                        current_blink_thread.join(timeout=1)
                    blink_stop_event.clear()
                    current_blink_thread = threading.Thread(target=lambda: blink_led(count), daemon=True)
                    current_blink_thread.start()
                    print(f"Started blinking LED on pin {GPIO_PIN_BLINK} {count} times.")
                    self.send_response(200)
                    self.end_headers()
                except Exception as e:
                    self.send_error(500, f"Error blinking GPIO: {e}")
            else:
                self.send_error(503, "GPIO control is not available")
        elif self.path == '/get_time':
            now_thailand = datetime.now(THAILAND_TIMEZONE)
            time_str = now_thailand.strftime("%H:%M:%S")
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(time_str.encode('utf-8'))
        elif self.path == '/get_latency':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"{last_frame_latency:.2f}".encode('utf-8'))
        elif self.path.startswith('/set_mouse_pos'):
            if GPIO_SUPPORT:
                try:
                    query_parts = self.path.split('?')[-1].split('&')
                    x = int(query_parts[0].split('=')[1])
                    y = int(query_parts[1].split('=')[1])
                    mouse_control_thread.set_pos(x, y)
                    self.send_response(200)
                    self.end_headers()
                except Exception as e:
                    self.send_error(500, f"Error setting mouse position: {e}")
            else:
                self.send_error(503, "GPIO control is not available")
        elif self.path == '/laser_on':
            if GPIO_SUPPORT:
                try:
                    laser.on()
                    self.send_response(200)
                    self.end_headers()
                except Exception as e:
                    self.send_error(500, f"Error controlling laser: {e}")
            else:
                self.send_error(503, "GPIO control is not available")
        elif self.path == '/laser_off':
            if GPIO_SUPPORT:
                try:
                    laser.off()
                    self.send_response(200)
                    self.end_headers()
                except Exception as e:
                    self.send_error(500, f"Error controlling laser: {e}")
            else:
                self.send_error(503, "GPIO control is not available")
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                pass
        else:
            self.send_error(404)
            self.end_headers()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def stream_camera(camera):
    global last_frame_latency
    frame_count = 0
    error_count = 0
    print("Starting camera streaming...")
    while True:
        start_time = time.time()  # Start timing for latency
        try:
            ret, frame = camera.read()
            if not ret:
                error_count += 1
                if error_count > 10:
                    camera.release()
                    time.sleep(1)
                    camera = cv2.VideoCapture(CAMERA_INDEX)
                    if camera.isOpened():
                        camera.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
                        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
                        error_count = 0
                continue
            error_count = 0
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb_frame)
            if img.size != RESOLUTION:
                img = img.resize(RESOLUTION, Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=JPEG_QUALITY)
            
            end_time = time.time()  # End timing for latency
            last_frame_latency = (end_time - start_time) * 1000 # Convert to milliseconds
            
            output.write(buffer.getvalue())
            frame_count += 1
            if frame_count % 100 == 0:
                print(f"Streamed {frame_count} frames successfully. Latency: {last_frame_latency:.2f} ms")
            time.sleep(1.0 / FRAMERATE)
        except Exception as e:
            print(f"Error in streaming: {e}")
            time.sleep(0.1)

def cleanup_gpio(signum, frame):
    print("\nReceived exit signal. Cleaning up GPIO...")
    if GPIO_SUPPORT:
        gpio_led_onoff.off()
        gpio_led_blink.off()
        blink_stop_event.set()
        mouse_control_thread.stop()
        laser.off()
        print(f"GPIO pins turned OFF.")
    exit(0)

def main():
    print("Simple MJPEG Streamer using OpenCV")
    print("===================================")
    signal.signal(signal.SIGINT, cleanup_gpio)
    signal.signal(signal.SIGTERM, cleanup_gpio)
    print(f"Opening camera {CAMERA_INDEX}...")
    cam = cv2.VideoCapture(CAMERA_INDEX)
    if not cam.isOpened():
        print("Error: Cannot open camera")
        exit(1)
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
    actual_width = int(cam.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera opened successfully")
    print(f"Resolution: {actual_width}x{actual_height}")
    ret, test_frame = cam.read()
    if not ret:
        print("Error: Cannot read from camera")
        cam.release()
        exit(1)
    print("Camera test successful")
    server = ThreadedHTTPServer(('', PORT), StreamingHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"\nServer started at http://0.0.0.0:{PORT}")
    print(f"View stream at http://localhost:{PORT}")
    print("Press Ctrl+C to stop\n")
    streaming_thread = threading.Thread(target=stream_camera, args=(cam,), daemon=True)
    streaming_thread.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        
if __name__ == '__main__':
    main()
