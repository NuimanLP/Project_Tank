# MJPG-Streamer with GPIO Control

## Overview
This modified version of mjpg-streamer includes GPIO control functionality for controlling a light or relay connected to GPIO pin 26.

## Features Added
- GPIO control endpoint at `/?action=gpio`
- Web interface with live stream and GPIO control buttons
- Real-time status updates
- JSON API for GPIO control

## Installation & Setup

### 1. Prerequisites
Make sure you have the necessary permissions to access GPIO:
```bash
# Add your user to the gpio group
sudo usermod -a -G gpio $USER
# Logout and login again for changes to take effect
```

### 2. Hardware Setup
Connect your LED or relay to:
- **GPIO Pin 26** (Physical pin 37 on Raspberry Pi)
- **Ground** (Any GND pin)
- Use appropriate resistor for LED (220-330 ohm)

### 3. Running the Application

#### Option 1: Using the startup script
```bash
./start_gpio.sh
```

#### Option 2: Manual start
```bash
export LD_LIBRARY_PATH="$(pwd)"
./mjpg_streamer -i "./input_uvc.so" -o "./output_http.so -w ./www -p 8080"
```

For Raspberry Pi camera:
```bash
./mjpg_streamer -i "./input_raspicam.so" -o "./output_http.so -w ./www -p 8080"
```

## Accessing the Interface

### Web Interface with GPIO Control
Open your browser and navigate to:
```
http://[YOUR_IP]:8080/stream_gpio.html
```

### API Endpoints

#### Get GPIO Status
```bash
curl http://[YOUR_IP]:8080/?action=gpio
```
Response:
```json
{"gpio": 0, "pin": 26, "status": "ok"}
```

#### Set GPIO Value
Turn ON:
```bash
curl http://[YOUR_IP]:8080/?action=gpio&value=1
```

Turn OFF:
```bash
curl http://[YOUR_IP]:8080/?action=gpio&value=0
```

## Troubleshooting

### Permission Issues
If you get permission errors accessing GPIO:
```bash
# Option 1: Run with sudo (not recommended for production)
sudo ./start_gpio.sh

# Option 2: Fix GPIO permissions
sudo chmod 666 /sys/class/gpio/export
sudo chmod 666 /sys/class/gpio/unexport
# After exporting pin 26:
sudo chmod 666 /sys/class/gpio/gpio26/direction
sudo chmod 666 /sys/class/gpio/gpio26/value
```

### Camera Not Found
- Check if camera is connected: `ls /dev/video*`
- For USB camera: ensure it's plugged in
- For Raspberry Pi camera: 
  - Enable camera: `sudo raspi-config`
  - Check connection: `vcgencmd get_camera`

### Build Issues
If you need to rebuild:
```bash
make clean
make
```

## Files Modified/Added
- `plugins/output_http/gpio_control.h` - GPIO control functions
- `plugins/output_http/httpd.c` - Added GPIO endpoint handler
- `plugins/output_http/output_http.c` - GPIO initialization
- `www/stream_gpio.html` - Web interface with GPIO controls
- `start_gpio.sh` - Startup script

## Safety Notes
- Always use appropriate resistors with LEDs
- For high-power devices, use relays or transistors
- Never exceed 3.3V on GPIO pins
- Maximum current per GPIO pin is typically 16mA

## License
This modification maintains the original GPL v2 license of mjpg-streamer.
