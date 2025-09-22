#!/usr/bin/env python3
import cv2
import io
import time
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from PIL import Image
import os
import signal # Import the signal module for graceful shutdown
from datetime import datetime # Import datetime
import pytz # Import pytz for timezone

# Check for RPi-specific libraries and import them.
# The gpiozero library is used for GPIO control.
try:
    from gpiozero import LED
    GPIO_PIN = 6  # Change the GPIO pin to 6
    gpio_led = LED(GPIO_PIN)
    print(f"GPIO pin {GPIO_PIN} initialized.")
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

class StreamingOutput(io.BufferedIOBase):
    """
    A class to hold the latest video frame and notify other threads when a new frame is available.
    """
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

# Global output stream
output = StreamingOutput()

class StreamingHandler(SimpleHTTPRequestHandler):
    """
    HTTP Handler to manage different types of requests from the web browser.
    """
    def log_message(self, format, *args):
        # Suppress log messages for cleaner output.
        pass
        
    def do_GET(self):
        """
        Handles GET requests.
        """
        if self.path == '/':
            # Redirect to the main page.
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            # Serve the HTML file from disk.
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
                
        # New endpoint to get the current Thai time
        elif self.path == '/time.json':
            try:
                bangkok_tz = pytz.timezone('Asia/Bangkok')
                now = datetime.now(bangkok_tz)
                th_time = now.strftime('%H:%M:%S')
                response = f'{{"th_time": "{th_time}"}}'.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', len(response))
                self.end_headers()
                self.wfile.write(response)
            except Exception as e:
                self.send_error(500, f"Error getting time: {e}")

        # New endpoints for GPIO control
        elif self.path == '/gpio_on':
            if GPIO_SUPPORT:
                try:
                    gpio_led.on()
                    print(f"GPIO pin {GPIO_PIN} turned ON")
                    self.send_response(200)
                    self.end_headers()
                except Exception as e:
                    self.send_error(500, f"Error controlling GPIO: {e}")
            else:
                self.send_error(503, "GPIO control is not available")
        elif self.path == '/gpio_off':
            if GPIO_SUPPORT:
                try:
                    gpio_led.off()
                    print(f"GPIO pin {GPIO_PIN} turned OFF")
                    self.send_response(200)
                    self.end_headers()
                except Exception as e:
                    self.send_error(500, f"Error controlling GPIO: {e}")
            else:
                self.send_error(503, "GPIO control is not available")
                
        elif self.path == '/stream.mjpg':
            # Handle the MJPEG video stream.
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
                # Close the connection on error.
                pass
        else:
            self.send_error(404)
            self.end_headers()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """
    A multi-threaded HTTP server to handle multiple requests concurrently.
    """
    daemon_threads = True

def stream_camera(camera):
    """
    Reads frames from the camera and streams them as JPEG.
    """
    frame_count = 0
    error_count = 0
    
    print("Starting camera streaming...")
    
    while True:
        try:
            # Capture frame-by-frame
            ret, frame = camera.read()
            
            if not ret:
                error_count += 1
                if error_count < 5:
                    print(f"Error reading frame (attempt {error_count})")
                time.sleep(0.1)
                
                # Try to reconnect after multiple failures
                if error_count > 10:
                    print("Too many errors, attempting to reconnect camera...")
                    camera.release()
                    time.sleep(1)
                    camera = cv2.VideoCapture(CAMERA_INDEX)
                    if camera.isOpened():
                        camera.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
                        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
                        print("Camera reconnected")
                        error_count = 0
                    else:
                        print("Failed to reconnect camera")
                        time.sleep(5)
                continue
            
            # Reset error count on successful frame
            error_count = 0
            
            # Convert BGR to RGB (OpenCV uses BGR by default)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Convert to PIL Image
            img = Image.fromarray(rgb_frame)
            
            # Resize if needed
            if img.size != RESOLUTION:
                img = img.resize(RESOLUTION, Image.LANCZOS)
            
            # Save to bytes buffer as JPEG
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=JPEG_QUALITY)
            
            # Write to output stream
            output.write(buffer.getvalue())
            
            frame_count += 1
            if frame_count % 100 == 0:
                print(f"Streamed {frame_count} frames successfully")
            
            # Control frame rate
            time.sleep(1.0 / FRAMERATE)
            
        except Exception as e:
            print(f"Error in streaming: {e}")
            time.sleep(0.1)

def cleanup_gpio(signum, frame):
    """
    Signal handler to ensure GPIO pin is turned off before exiting.
    """
    print("\nReceived exit signal. Cleaning up GPIO...")
    if GPIO_SUPPORT:
        gpio_led.off()
        print(f"GPIO pin {GPIO_PIN} turned OFF.")
    exit(0)

def main():
    print("Simple MJPEG Streamer using OpenCV")
    print("===================================")
    
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, cleanup_gpio)
    signal.signal(signal.SIGTERM, cleanup_gpio)
    
    # Open camera
    print(f"Opening camera {CAMERA_INDEX}...")
    cam = cv2.VideoCapture(CAMERA_INDEX)
    
    if not cam.isOpened():
        print("Error: Cannot open camera")
        print("Please check:")
        print("  1. Camera is connected")
        print("  2. Camera index is correct (try 0, 1, 2...)")
        print("  3. No other application is using the camera")
        exit(1)
    
    # Set camera resolution
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
    
    # Get actual resolution (camera might not support requested resolution)
    actual_width = int(cam.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera opened successfully")
    print(f"Resolution: {actual_width}x{actual_height}")
    
    # Test camera by reading one frame
    ret, test_frame = cam.read()
    if not ret:
        print("Error: Cannot read from camera")
        cam.release()
        exit(1)
    print("Camera test successful")
    
    # Start HTTP server in a thread
    server = ThreadedHTTPServer(('', PORT), StreamingHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    
    print(f"\nServer started at http://0.0.0.0:{PORT}")
    print(f"View stream at http://localhost:{PORT}")
    print("Press Ctrl+C to stop\n")
    
    # Start streaming thread
    streaming_thread = threading.Thread(target=stream_camera, args=(cam,), daemon=True)
    streaming_thread.start()
    
    try:
        # Keep running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        
if __name__ == '__main__':
    main()
