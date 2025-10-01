# Motor PWM Reading Fix

## Problem
The motor speed display was reading values from the joystick commands (FR and LR) instead of reading the actual motor PWM values from the Arduino.

## Changes Made

### 1. Updated `read_serial_data_thread()` function
**File**: `web_fixed.py`

Added parsing for M1 and M2 messages from Arduino:
- Added `motor_m1_speed` and `motor_m2_speed` to the global declaration
- Added `elif` blocks to parse `M1:xxx` and `M2:xxx` messages from serial
- Motor PWM values are now read directly from Arduino (-255 to 255)

```python
# Arduino sends: M1:XXX or M2:XXX (motor PWM values -255 to 255)
elif line.startswith("M1:"):
    try:
        motor_value = line.split(':')[1]
        motor_m1_speed = int(motor_value)
        print(f"Motor M1 PWM Received: {motor_m1_speed}")
    except:
        pass # Ignore malformed lines

elif line.startswith("M2:"):
    try:
        motor_value = line.split(':')[1]
        motor_m2_speed = int(motor_value)
        print(f"Motor M2 PWM Received: {motor_m2_speed}")
    except:
        pass # Ignore malformed lines
```

### 2. Removed incorrect motor speed assignment
**File**: `web_fixed.py` - `/tank_command` handler

Removed these lines that were incorrectly reading from joystick:
```python
# REMOVED - These were reading from joystick, not from Arduino
motor_m1_speed = command_data.get('FR', 0)
motor_m2_speed = command_data.get('LR', 0)
print(f"Motor speeds updated - M1: {motor_m1_speed}, M2: {motor_m2_speed}")
```

## How It Works Now

1. **User input**: Joystick sends FR and LR commands to Raspberry Pi
2. **Raspberry Pi**: Forwards commands to Arduino via serial
3. **Arduino**: 
   - Receives commands
   - Calculates actual motor PWM values (-255 to 255)
   - Sends back actual PWM values as `M1:xxx` and `M2:xxx`
4. **Raspberry Pi**: 
   - Reads M1 and M2 values from serial
   - Updates global `motor_m1_speed` and `motor_m2_speed` variables
5. **Web UI**: Fetches and displays actual motor PWM values via `/get_motor_speeds` endpoint

## Testing
Run the web server:
```bash
python3 web_fixed.py
```

You should now see:
- "Motor M1 PWM Received: xxx" messages showing actual Arduino PWM values
- "Motor M2 PWM Received: xxx" messages showing actual Arduino PWM values
- Web UI displaying the real motor speeds, not joystick values

## Backup
A backup of the previous version was saved as:
`web_fixed.py.backup`
