import keyboard
from gpiozero import LED
import time

# Define the GPIO pins for each key.
# We'll use GPIO 26, 20, 21, and 16 as an example.
# You can change these to any available GPIO pins.
pin_w = LED(6)
pin_a = LED(20)
pin_s = LED(21)
pin_d = LED(16)

# Create a dictionary to map keys to GPIO pins
gpio_map = {
    'w': pin_w,
    'a': pin_a,
    's': pin_s,
    'd': pin_d
}

print("Listening for WASD key presses...")
print("Press ESC to exit.")

try:
    while True:
        # Wait for any key to be pressed
        key_event = keyboard.read_event()

        if key_event.event_type == keyboard.KEY_DOWN:
            key = key_event.name
            
            # Check if the pressed key is in our map
            if key in gpio_map:
                print(f"Key '{key}' pressed. Turning ON corresponding GPIO pin.")
                gpio_map[key].on()
            
            # Exit loop if 'esc' is pressed
            if key == 'esc':
                print("Exiting program.")
                break

        elif key_event.event_type == keyboard.KEY_UP:
            key = key_event.name
            
            # Turn OFF the corresponding GPIO pin when the key is released
            if key in gpio_map:
                print(f"Key '{key}' released. Turning OFF corresponding GPIO pin.")
                gpio_map[key].off()

except Exception as e:
    print(f"An error occurred: {e}")
finally:
    # Ensure all pins are turned off on exit
    for pin in gpio_map.values():
        pin.off()
    print("All GPIO pins are now OFF.")
