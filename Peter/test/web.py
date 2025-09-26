#!/usr/bin/env python3
# web.py (Python 3)

import serial
import time
import signal
import sys
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- Serial Communication Configuration ---
# 🚨 IMPORTANT: Change this to match your Arduino's port 🚨
SERIAL_PORT = '/dev/ttyACM0' 
SERIAL_BAUDRATE = 115200 
ser = None 

# --- Web Server Configuration ---
HOST_NAME = '0.0.0.0'
PORT_NUMBER = 8080

# --- Motor Control Mapping ---
# Maps the joystick "count" value from index.html to a serial command character
MOVEMENT_MAP = {
    1: 'W',  # Up -> Forward
    2: 'D',  # Right -> Turn Right
    3: 'S',  # Down -> Reverse
    4: 'A',  # Left -> Turn Left
    0: 'X'   # Stop/Release -> Stop
}

# --- Serial Command Function ---
def send_serial_command(command):
    global ser
    if ser and ser.is_open:
        try:
            # Send the command character followed by a newline for clear reading on Arduino
            command_str = (command + '\n').encode('utf-8')
            ser.write(command_str)
            # print(f"Serial: Sent '{command}'") # Optional: Uncomment for debugging
        except serial.SerialException as e:
            print(f"Serial Error: Could not send command: {e}")
    # else:
    #     print("Serial port is not open or configured.") # Optional: Uncomment for debugging

# --- HTTP Request Handler ---
class StreamingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Serve the main control page
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            with open('index.html', 'rb') as f:
                self.wfile.write(f.read())
            return
        
        # Handle the joystick/WASD commands
        elif self.path.startswith('/gpio_blink'):
            try:
                query = self.path.split('?')[-1]
                count_str = query.split('=')[-1]
                count = int(count_str)
                
                command = MOVEMENT_MAP.get(count, 'X') # Default to 'X' (Stop)
                send_serial_command(command)
                
                self.send_response(200)
                self.end_headers()
            except Exception as e:
                self.send_error(500, f"Error processing command: {e}")
            return

        # Serve other files (like the mjpeg stream, though not fully implemented here)
        # ... (You can add code here for video streaming if needed) ...
        
        # 404 Not Found for other paths
        self.send_error(404, 'File Not Found')

# --- Cleanup and Main Functions ---
def cleanup(signum, frame):
    global ser
    print("\nReceived exit signal. Cleaning up...")
    
    # 🚨 SERIAL PORT CLOSING 🚨
    if ser and ser.is_open:
        send_serial_command('X') # Send a final stop command
        ser.close()
        print("Serial Port Closed.")
        
    print("Exiting application.")
    sys.exit(0)

def main():
    global ser
    
    # 🚨 SERIAL PORT OPENING 🚨
    try:
        # Open serial port
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)
        time.sleep(2) # Wait for the port to initialize (crucial for Arduino)
        print(f"Serial Port {SERIAL_PORT} opened successfully.")
    except serial.SerialException as e:
        print(f"WARNING: Could not open Serial Port {SERIAL_PORT}. Motors will not work. Error: {e}")
        ser = None
        
    # Setup signal handlers for graceful exit
    signal.signal(signal.SIGINT, cleanup)  # Ctrl+C
    signal.signal(signal.SIGTERM, cleanup) # kill command

    # Start the web server
    server_class = HTTPServer
    httpd = server_class((HOST_NAME, PORT_NUMBER), StreamingHandler)
    print(time.asctime(), "Server Starts - %s:%s" % (HOST_NAME, PORT_NUMBER))
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        cleanup(None, None) # Ensure cleanup runs

if __name__ == '__main__':
    main()
