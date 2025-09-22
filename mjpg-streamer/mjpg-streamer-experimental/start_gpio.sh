#!/bin/bash

# MJPG-Streamer with GPIO Control for Raspberry Pi 5
# Physical pin 26 = GPIO 597 on Raspberry Pi 5

GPIO_PIN=597

echo "Starting MJPG-Streamer with GPIO Control..."
echo "GPIO Pin 597 (physical pin 26) will be used for light control"
echo ""

# Make sure GPIO is exported and configured
if [ ! -d /sys/class/gpio/gpio$GPIO_PIN ]; then
    echo "Exporting GPIO $GPIO_PIN..."
    echo $GPIO_PIN | sudo tee /sys/class/gpio/export > /dev/null
    sleep 0.5
fi

# Always set direction and permissions
echo "Configuring GPIO $GPIO_PIN..."
echo out | sudo tee /sys/class/gpio/gpio$GPIO_PIN/direction > /dev/null
sudo chmod 666 /sys/class/gpio/gpio$GPIO_PIN/value
sudo chmod 666 /sys/class/gpio/gpio$GPIO_PIN/direction

# Test the GPIO
echo "Testing GPIO (LED should blink once)..."
echo 1 > /sys/class/gpio/gpio$GPIO_PIN/value
sleep 0.5
echo 0 > /sys/class/gpio/gpio$GPIO_PIN/value
echo "GPIO test complete"
echo ""

echo "Access the stream with GPIO control at:"
echo "  http://$(hostname -I | cut -d' ' -f1):8080/stream_gpio.html"
echo ""
echo "Or access the standard interface at:"
echo "  http://$(hostname -I | cut -d' ' -f1):8080/"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Set library path
export LD_LIBRARY_PATH="$(pwd)"

# Trap to cleanup on exit
trap "echo 'Cleaning up...'; echo 0 > /sys/class/gpio/gpio$GPIO_PIN/value" EXIT

# Start mjpg-streamer
./mjpg_streamer -i "./input_uvc.so -d /dev/video0 -r 640x480 -f 30" \
                -o "./output_http.so -w ./www -p 8080"
