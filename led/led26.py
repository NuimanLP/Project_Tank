from gpiozero import LED
from time import sleep

# Define the GPIO pin. Use the Broadcom (BCM) numbering scheme.
# GPIO26 corresponds to physical pin 37 on the Raspberry Pi header.
led = LED(26)

# Turn the LED (or connected device) ON
print("Turning GPIO26 ON...")
led.on()

# Keep the pin ON for a few seconds to verify the action
sleep(10)

# Turn the LED (or connected device) OFF
print("Turning GPIO26 OFF...")
led.off()
