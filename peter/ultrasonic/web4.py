#!/usr/bin/env python3
import cv2
import io
import time
import threading
# Note: The existing code uses SimpleHTTPRequestHandler but is structured like a server
# I will keep the existing server/handler setup to maintain compatibility.
from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from PIL import Image
import os
import signal
from datetime import datetime
import pytz

try:
    import serial
except ImportError:
    print("Error: pyserial library not found. Please install it with: pip install pyserial")
    exit(1)

try:
    from gpiozero import LED, Servo
    GPIO_PIN_ONOFF = 6
    GPIO_PIN_BLINK = 26
    GPIO_PAN = 17 # Original GPIO pin for Pan (left/right) servo (Now disabled for Stepper)
    GPIO_TILT = 18 # GPIO pin for Tilt (up/down) servo (Still active)
    GPIO_LASER = 27 # GPIO pin for laser
    
    gpio_led_onoff = LED(GPIO_PIN_ONOFF)
    gpio_led_blink = LED(GPIO_PIN_BLINK)
    pan_servo = Servo(GPIO_PAN) # Still initialized but Pan logic moved to Serial
    tilt_servo = Servo(GPIO_TILT)
    laser = LED(GPIO_LASER)
    print(f"GPIO pins {GPIO_PIN_ONOFF}, {GPIO_PIN_BLINK}, {GPIO_PAN}, {GPIO_TILT}, and {GPIO_LASER} initialized.")
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
SERIAL_PORT = '/dev/ttyACM0' # Common port for Arduino on Pi. 
BAUDRATE = 115200
# ----------------------------------------------------
# Stepper Control Configuration
MAX_STEPS_PER_COMMAND = 10 # Maximum steps to send to Arduino per mouse/joystick update
# The X position range is +/- RESOLUTION[0]/2 = +/- 320
X_POS_RANGE = RESOLUTION[0] / 2 # 320
X_SCALE_FACTOR = X_POS_RANGE / MAX_STEPS_PER_COMMAND # 320 / 10 = 32
# --- NEW: Fixed step size for D-Pad control ---
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
# Function to send command via UART (Unchanged)
def send_command_to_arduino(command):
    global ser
    if ser is None:
        print("Serial port not initialized.")
        return

    with serial_lock:
        try:
            ser.write(command.encode('utf-8'))
            print(f"UART: Sent command '{command.strip()}' to Arduino.")
        except Exception as e:
            print(f"UART Error sending command: {e}")
# ----------------------------------------------------

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
                    
                    # Arduino sends: Dist:XXX
                    if line.startswith("Dist:"):
                        try:
                            # Extract the numeric part
                            distance_value = line.split(':')[1]
                            ultrasonic_distance = distance_value 
                            # print(f"Distance Received: {ultrasonic_distance} cm") # Debugging
                        except:
                            pass # Ignore malformed lines
                            
        except Exception as e:
            print(f"Serial reading thread error: {e}")
            break
        time.sleep(0.01) # Short delay to prevent high CPU usage


class MouseControlThread(threading.Thread):
    """
    Handles local GPIO Servo control for TILT (Y-axis).
    The PAN control (X-axis) is now handled via Serial/Stepper motor.
    """
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.x = 0
        self.y = 0
        self.running = True
        self.lock = threading.Lock()
        # Track the current tilt angle for incremental adjustments (D-Pad)
        self.current_tilt_angle = 0
        self.PAN_RANGE = 90
        self.TILT_RANGE = 45

    def set_pos(self, x, y):
        """Sets the target position (used by mouse-drag)"""
        with self.lock:
            self.x = x
            self.y = y

    def adjust_tilt(self, delta_angle):
        """Adjusts the tilt angle incrementally (used by D-Pad)"""
        with self.lock:
            new_angle = self.current_tilt_angle + delta_angle
            self.current_tilt_angle = max(-self.TILT_RANGE, min(self.TILT_RANGE, new_angle))
            # Apply immediately
            if GPIO_SUPPORT:
                tilt_servo.value = self.current_tilt_angle / 90.0
                # No need to set target_y as the run loop will use the new current_tilt_angle
                # But we should update the target_y to match the new angle if we wanted to be perfectly consistent with Mouse Drag
                # For simplicity, we let the tilt adjustment happen outside the run loop for immediate response
        
    def run(self):
        if not GPIO_SUPPORT:
            return

        VIDEO_HEIGHT = RESOLUTION[1]
        HALF_VIDEO_HEIGHT = VIDEO_HEIGHT / 2
        
        while self.running:
            with self.lock:
                # target_x = self.x # X is handled by Stepper/Serial now
                target_y = self.y # This is the Y offset from center (mouse drag)
                current_tilt_angle = self.current_tilt_angle
            
            # --- TILT SERVO CONTROL (Still active - controlled by mouse drag) ---
            # Mouse drag calculates target angle based on position (target_y)
            target_tilt_angle = (target_y / HALF_VIDEO_HEIGHT) * self.TILT_RANGE
            target_tilt_angle = max(-self.TILT_RANGE, min(self.TILT_RANGE, target_tilt_angle))

            # Only move if the drag target angle is significantly different from the current angle
            if abs(target_tilt_angle - current_tilt_angle) > 1:
                # Smooth transition towards the dragged target position
                self.current_tilt_angle += (target_tilt_angle - current_tilt_angle) * 0.1
                # Control the TILT servo
                tilt_servo.value = self.current_tilt_angle / 90.0

            time.sleep(0.01)

    def stop(self):
        self.running = False

mouse_control_thread = MouseControlThread()
if GPIO_SUPPORT:
    mouse_control_thread.start()

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
        
        elif self.path.startswith('/tank_command'):
            try:
                query = self.path.split('?')[-1]
                command = query.split('=')[-1].upper()
                
                if command in ['W', 'A', 'S', 'D', 'X']:
                    send_command_to_arduino(command)
                    self.send_response(200)
                    self.end_headers()
                else:
                    self.send_error(400, "Invalid Tank Command")
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
            
        # --- NEW: Turret Directional D-Pad/Joystick Control Logic ---
        elif self.path.startswith('/turret_move'):
            if GPIO_SUPPORT:
                try:
                    query = self.path.split('?')[-1]
                    direction = query.split('=')[1].upper()
                    
                    steps_to_move = 0
                    
                    if direction == 'L':
                        steps_to_move = -TURRET_STEP_DELTA # Pan Left (Stepper)
                    elif direction == 'R':
                        steps_to_move = TURRET_STEP_DELTA  # Pan Right (Stepper)
                    elif direction == 'U':
                        # Tilt Up (Servo, controlled locally on Pi)
                        mouse_control_thread.adjust_tilt(TURRET_TILT_DELTA_ANGLE)
                    elif direction == 'D':
                        # Tilt Down (Servo, controlled locally on Pi)
                        mouse_control_thread.adjust_tilt(-TURRET_TILT_DELTA_ANGLE)
                        
                    if abs(steps_to_move) > 0:
                        # Command format: P[Steps]\n
                        command = f"P{steps_to_move}\n"
                        send_command_to_arduino(command)
                        
                    self.send_response(200)
                    self.end_headers()
                    
                except Exception as e:
                    print(f"Error processing /turret_move: {e}")
                    self.send_error(500, f"Error moving turret: {e}")
            else:
                self.send_error(503, "GPIO control is not available")
        # --- END TURRET DIRECTIONAL CONTROL LOGIC ---

        elif self.path.startswith('/set_mouse_pos'):
            # This endpoint still handles the original click-and-drag based positioning
            if GPIO_SUPPORT:
                try:
                    query_parts = self.path.split('?')[-1].split('&')
                    # Note: We assume x is the first param, y is the second
                    x_str = query_parts[0].split('=')[1]
                    y_str = query_parts[1].split('=')[1]
                    
                    x = int(x_str)
                    y = int(y_str)
                    
                    # 1. Calculate steps for Stepper Pan (X-axis)
                    # Scale X from +/- 320 (approx) to +/- 10 steps
                    steps_to_move = int(x / X_SCALE_FACTOR)
                    
                    # Ensure steps is within bounds [-MAX_STEPS_PER_COMMAND, MAX_STEPS_PER_COMMAND]
                    steps_to_move = max(-MAX_STEPS_PER_COMMAND, min(MAX_STEPS_PER_COMMAND, steps_to_move))
                    
                    if abs(steps_to_move) > 0:
                        # Command format: P[Steps]\n
                        command = f"P{steps_to_move}\n"
                        send_command_to_arduino(command)
                        
                    # 2. Control Servo Tilt (Y-axis)
                    # Pass X and Y to the thread. The thread's 'run' method only uses Y now.
                    mouse_control_thread.set_pos(x, y) 

                    self.send_response(200)
                    self.end_headers()
                except Exception as e:
                    print(f"Error processing /set_mouse_pos: {e}")
                    self.send_error(500, f"Error setting mouse/stepper position: {e}")
            else:
                self.send_error(503, "GPIO control is not available")
        # --- END STEPPER PAN CONTROL LOGIC ---
        
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
        gpio_led_onoff.off()
        gpio_led_blink.off()
        blink_stop_event.set()
        if 'mouse_control_thread' in globals() and mouse_control_thread.is_alive():
            mouse_control_thread.stop()
        laser.off()
        print(f"GPIO pins turned OFF.")
    
    if ser and ser.is_open:
        try:
            ser.write('X'.encode('utf-8'))
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
        send_command_to_arduino('X') 
        
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
