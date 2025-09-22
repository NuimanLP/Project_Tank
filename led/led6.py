from gpiozero import LED
from time import sleep

# Define the GPIO pin. Use the Broadcom (BCM) numbering scheme.
# GPIO6 corresponds to a different physical pin on the Raspberry Pi header.
led = LED(6)  # <-- แก้ตรงนี้!

# Turn the LED (or connected device) ON
print("Turning GPIO6 ON...")
led.on()

# Keep the pin ON for a few seconds to verify the action
sleep(5)

# Turn the LED (or connected device) OFF
print("Turning GPIO6 OFF...")
led.off()
