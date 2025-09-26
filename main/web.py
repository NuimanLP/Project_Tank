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
    # ----------------------------------------------------
    # NEW: Import serial library
    import serial
    # ----------------------------------------------------
except ImportError:
    print("Error: pyserial library not found.")
    print("Please install it with: pip install pyserial")
    exit(1)

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
# ----------------------------------------------------
# NEW: Serial Port Configuration
SERIAL_PORT = '/dev/ttyACM0'  # Common port for Arduino on Pi. Use '/dev/ttyS0' for hardware UART
BAUDRATE = 115200
# ----------------------------------------------------

# Set Thailand timezone
THAILAND_TIMEZONE = pytz.timezone('Asia/Bangkok')

# ----------------------------------------------------
# NEW: Global Serial Object and Lock
# The serial object should be global to be accessible across threads/functions
ser = None
# A lock is crucial for multi-threading to prevent sending corrupted data simultaneously
serial_lock = threading.Lock() 
# ----------------------------------------------------


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

# ----------------------------------------------------
# NEW: Function to send command via UART
def send_command_to_arduino(command):
    """
    Sends a single character command to the Arduino via Serial/UART.
    
    The command should be a single character: 'W', 'A', 'S', 'D', or 'X' (Stop).
    """
    global ser
    if ser is None:
        print("Serial port not initialized.")
        return

    # Acquire the lock to ensure only one thread sends data at a time
    with serial_lock:
        try:
            # Encode the string command to bytes, as serial.write expects bytes
            ser.write(command.encode('utf-8'))
            print(f"UART: Sent command '{command}' to Arduino.")
        except Exception as e:
            print(f"UART Error sending command: {e}")

# ----------------------------------------------------


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
        # No need to join in this simple example, but good practice in complex apps
        # self.join() 

mouse_control_thread = MouseControlThread()
if GPIO_SUPPORT:
    mouse_control_thread.start()

class StreamingHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        global current_blink_thread, blink_stop_event
        
        # --- Existing code for static files and video stream is here ---
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
        
        # --- GPIO and Time/Latency endpoints ---
        # The original /gpio_blink has been commented out or removed
        # as it's replaced by the new /tank_command endpoint for tank movement.
        
        # Original GPIO endpoints (ON/OFF, Laser) remain, as they are separate actions
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
        
        # ----------------------------------------------------
        # NEW: Endpoint for sending Tank commands to Arduino
        elif self.path.startswith('/tank_command'):
            try:
                # The command is passed as a query parameter: /tank_command?cmd=W
                query = self.path.split('?')[-1]
                command = query.split('=')[-1].upper() # Ensure command is uppercase
                
                # Validate the command
                if command in ['W', 'A', 'S', 'D', 'X']: # W, A, S, D, X (stop)
                    send_command_to_arduino(command)
                    self.send_response(200)
                    self.end_headers()
                else:
                    self.send_error(400, "Invalid Tank Command")
            except Exception as e:
                self.send_error(500, f"Error sending tank command: {e}")
        # ----------------------------------------------------
        
        # The original /gpio_blink is now commented out or replaced, 
        # as its functionality is superseded by /tank_command for movement.
        # elif self.path.startswith('/gpio_blink'):
        #     ... (Removed/replaced for clarity and purpose)

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
                    # Optional: Send 'FIRE' command to Arduino for a separate action
                    # send_command_to_arduino('F') 
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
    # ... (Unchanged) ...
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
    global ser
    print("\nReceived exit signal. Cleaning up...")
    if GPIO_SUPPORT:
        gpio_led_onoff.off()
        gpio_led_blink.off()
        blink_stop_event.set()
        if 'mouse_control_thread' in globals() and mouse_control_thread.is_alive():
             mouse_control_thread.stop()
        laser.off()
        print(f"GPIO pins turned OFF.")
    
    # ----------------------------------------------------
    # NEW: Clean up Serial Port
    if ser and ser.is_open:
        try:
            # Send 'X' (stop) command before closing
            ser.write('X'.encode('utf-8'))
            time.sleep(0.1)
            ser.close()
            print("Serial port closed.")
        except Exception as e:
            print(f"Error closing serial port: {e}")
    # ----------------------------------------------------
            
    os._exit(0) # Use os._exit to forcefully terminate all threads

def main():
    global ser
    print("Simple MJPEG Streamer using OpenCV")
    print("===================================")
    signal.signal(signal.SIGINT, cleanup_gpio)
    signal.signal(signal.SIGTERM, cleanup_gpio)
    
    # ----------------------------------------------------
    # NEW: Initialize Serial Port
    try:
        # ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.1)
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=0.1 # Timeout for read operations
        )
        print(f"Successfully opened serial port {SERIAL_PORT} at {BAUDRATE} baud.")
        # Send an initial stop command
        send_command_to_arduino('X') 
    except serial.SerialException as e:
        print(f"Error: Could not open serial port {SERIAL_PORT}. Check connection and permissions.")
        print(f"Details: {e}")
        # Continue running the server without Arduino control
        ser = None
    # ----------------------------------------------------
        
    print(f"Opening camera {CAMERA_INDEX}...")
    cam = cv2.VideoCapture(CAMERA_INDEX)
    if not cam.isOpened():
        print("Error: Cannot open camera")
        # Ensure cleanup runs even on camera failure
        cleanup_gpio(None, None) 
    # ... (Rest of camera setup and server start is unchanged) ...
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
        cleanup_gpio(None, None)
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
