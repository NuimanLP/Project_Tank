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
import urllib.parse
from typing import Dict, Any

try:
    import serial
except ImportError:
    print("Error: pyserial library not found. Please install it with: pip install install pyserial")
    exit(1)

try:
    from gpiozero import LED, Servo
    GPIO_SUPPORT = True
except ImportError:
    print("Warning: gpiozero library not found. GPIO control will be disabled.")
    GPIO_SUPPORT = False

# Configuration
PORT = 8080
RESOLUTION = (640, 480)
FRAMERATE = 24
JPEG_QUALITY = 80
CAMERA_INDEX = 0
# ----------------------------------------------------
SERIAL_PORT = '/dev/ttyAMA0' # Common port for Arduino on Pi. 
BAUDRATE = 115200
# ----------------------------------------------------
# Stepper Control Configuration
MAX_STEPS_PER_COMMAND = 10 # Maximum steps to send to Arduino per mouse/joystick update
# The X position range is +/- RESOLUTION[0]/2 = +/- 320
X_POS_RANGE = RESOLUTION[0] / 2 # 320
X_SCALE_FACTOR = X_POS_RANGE / MAX_STEPS_PER_COMMAND # 320 / 10 = 32
# --- NEW: Fixed step size for D-Pad control (Now repurposed for J/K keys in index.html) ---
TURRET_STEP_DELTA = 3 # Fixed steps for Stepper Pan
TURRET_TILT_DELTA_ANGLE = 5 # Fixed angle change for Servo Tilt
# ----------------------------------------------------


# Set Thailand timezone
THAILAND_TIMEZONE = pytz.timezone('Asia/Bangkok')

# ----------------------------------------------------
# Global Serial Object, Lock, and Sensor Data
ser = None
serial_lock = threading.Lock()
ultrasonic_distance = "N/A" # Variable to store the distance value (cm)
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


# Thread for Reading Ultrasonic Data from Arduino (Unchanged)
def read_serial_data_thread():
    """Continuously reads data from the Arduino serial port for sensor values."""
    global ser, ultrasonic_distance
    print("Starting Arduino serial data reader thread...")
    if ser is None:
        print("Serial reader skipped: Serial port not available.")
        return
        
    while True:
        try:
            with serial_lock:
                if ser.in_waiting > 0:
                    # Read until a newline character (Arduino's Serial.println())
                    line = ser.readline().decode('utf-8').strip()
                    print(line)
                    # Arduino sends: Dist:XXX or Dist:ERROR
                    if line.startswith("Dist:"):
                        try:
                            # Extract the numeric part
                            distance_value = line.split(':')[1]
                            if distance_value == "ERROR":
                                ultrasonic_distance = "N/A"
                                print("Distance Error: Sensor timeout or out of range")
                            else:
                                ultrasonic_distance = distance_value 
                                print(f"Distance Received: {ultrasonic_distance} cm") # Debugging
                        except:
                            ultrasonic_distance = "N/A"
                            pass # Ignore malformed lines
                            
        except Exception as e:
            print(f"Serial reading thread error: {e}")
            ultrasonic_distance = "N/A"
            break
        time.sleep(0.01) # Short delay to prevent high CPU usage


def parse_tank_command(path: str) -> Dict[str, int]:
    """
    Parses the command from a URL path, decodes it, and returns a dictionary 
    with FR and LR values as integers.
    
    :param path: The self.path string from the server request.
    :return: A dictionary like {'FR': 0, 'LR': 0}.
    """
    # 1. Separate the path into the base and the query string
    _, query_string = urllib.parse.splitquery(path)

    if not query_string:
        return {} # Handle case with no query string

    # 2. Use parse_qs to automatically decode and parse the standard query parameters
    # The result is a dictionary where values are lists of strings
    parsed_params = urllib.parse.parse_qs(query_string)

    # 3. Get the 'cmd' value (it will be URL-decoded: 'FR:0;LR:0')
    command_str = parsed_params.get('cmd', [''])[0]
    
    # 4. Split the command string by the semicolon separator
    command_parts = command_str.split(';')
    
    result = {}
    for part in command_parts:
        # 5. Split each part by the colon separator
        if ':' in part:
            key, value_str = part.split(':', 1)
            # 6. Store the key (FR/LR) and convert the value to an integer
            try:
                result[key.upper()] = int(value_str)
            except ValueError:
                print(f"Warning: Could not convert value '{value_str}' to integer for key '{key}'")
                
    return result


class StreamingHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
        
    def do_GET(self):
        global current_blink_thread, blink_stop_event, ultrasonic_distance
        
        # --- Existing code for static files, GPIO, and video stream ---
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            try:
                with open('index_fixed.html', 'rb') as f:
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
                with open(self.path[1:], 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'audio/mpeg')
                self.send_header('Content-Length', len(content))
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, 'File Not Found: %s' % self.path)
            
        elif self.path.startswith('/tank_command'):
            try:
                self.send_response(200)
                self.end_headers()
                # print(self.path)
                command_data = parse_tank_command(self.path)
                # print(command_data)

                global ser
                if ser is None:
                    print("Serial port not initialized.")
                    return

                command_str = f"FR:{command_data['FR']};LR:{command_data['LR']};UD:{command_data['UD']};TLR:{command_data['TLR']};FC:{command_data['FC']}" # "FR:5;LR:0"
                message_to_send = command_str + '\n'
                with serial_lock:
                    ser.write(message_to_send.encode('utf-8'))

            except Exception as e:
                self.send_error(500, f"Error sending tank command: {e}")
        

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
            
        # Endpoint to fetch real-time ultrasonic distance
        elif self.path == '/get_distance':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            # Send the global variable value updated by the serial reader thread
            self.wfile.write(str(ultrasonic_distance).encode('utf-8'))
            
        elif self.path == '/laser_on':
            try:
                # laser.on()
                self.send_response(200)
                self.end_headers()
            except Exception as e:
                self.send_error(500, f"Error controlling laser: {e}")
                
        elif self.path == '/laser_off':
            try:
                # laser.on()
                self.send_response(200)
                self.end_headers()
            except Exception as e:
                self.send_error(500, f"Error controlling laser: {e}")

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
        start_time = time.time()
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
            
            end_time = time.time()
            last_frame_latency = (end_time - start_time) * 1000
            
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

        blink_stop_event.set()
        # if 'mouse_control_thread' in globals() and mouse_control_thread.is_alive():
        #     mouse_control_thread.stop()

        print(f"GPIO pins turned OFF.")
    
    if ser and ser.is_open:
        try:
            # ser.write('X'.encode('utf-8')) # Stop command to Arduino
            time.sleep(0.1)
            ser.close()
        except Exception as e:
            print(f"Error closing serial port: {e}")
    os._exit(0)

def main():
    global ser
    print("Simple MJPEG Streamer using OpenCV")
    print("===================================")
    signal.signal(signal.SIGINT, cleanup_gpio)
    signal.signal(signal.SIGTERM, cleanup_gpio)
    
    # ----------------------------------------------------
    # Initialize Serial Port
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=0.1
        )
        print(f"Successfully opened serial port {SERIAL_PORT} at {BAUDRATE} baud.")
        # Send stop command to Arduino
        # send_command_to_arduino('X') 
        
        # START SERIAL READER THREAD
        serial_reader_thread = threading.Thread(target=read_serial_data_thread, daemon=True)
        serial_reader_thread.start()
        
    except serial.SerialException as e:
        print(f"Error: Could not open serial port {SERIAL_PORT}. Check connection and permissions.")
        print(f"Details: {e}")
        ser = None
    # ----------------------------------------------------
    
    print(f"Opening camera {CAMERA_INDEX}...")
    cam = cv2.VideoCapture(CAMERA_INDEX)
    if not cam.isOpened():
        print("Error: Cannot open camera")
        cleanup_gpio(None, None)
    
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
