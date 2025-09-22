#!/usr/bin/env python3
import cv2
import io
import time
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from PIL import Image

# Configuration
PORT = 8080
RESOLUTION = (640, 480)
FRAMERATE = 24
JPEG_QUALITY = 80
CAMERA_INDEX = 0

class StreamingOutput(io.BufferedIOBase):
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
    def log_message(self, format, *args):
        # Suppress log messages for cleaner output
        pass
        
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = '''
<html>
<head>
<title>Camera MJPEG Stream</title>
<style>
body {
    background-color: #333;
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
    margin: 0;
    font-family: Arial, sans-serif;
}
.container {
    text-align: center;
}
h1 {
    color: white;
    margin-bottom: 20px;
}
img {
    border: 2px solid #555;
    box-shadow: 0 0 20px rgba(0,0,0,0.5);
    max-width: 100%;
    height: auto;
}
.info {
    color: #ccc;
    margin-top: 20px;
}
.status {
    color: #4CAF50;
    margin-top: 10px;
}
</style>
</head>
<body>
<div class="container">
<h1>Camera MJPEG Stream</h1>
<img src="stream.mjpg" width="640" height="480" />
<div class="info">
    <p>Direct stream URL: <a href="/stream.mjpg" style="color: #4CAF50;">/stream.mjpg</a></p>
    <p class="status">✓ Streaming active</p>
</div>
</div>
</body>
</html>
'''
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
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
    """Handle requests in a separate thread."""
    daemon_threads = True

def stream_camera(camera):
    """Stream camera frames as JPEG"""
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

def main():
    print("Simple MJPEG Streamer using OpenCV")
    print("===================================")
    
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
        cam.release()
        print("Camera released")
        print("Server stopped")

if __name__ == '__main__':
    main()