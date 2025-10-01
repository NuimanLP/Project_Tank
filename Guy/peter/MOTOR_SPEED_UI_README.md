# Motor Speed UI Enhancement - Signed Values with Color Coding

## Overview
Added real-time motor speed display to the web interface showing M1 and M2 motor speeds with:
- Range: -255 to 255 (negative for reverse, positive for forward)
- Color coding: RED for negative values, GREEN for positive values
- Bidirectional progress bars with center reference point

## Changes Made

### 1. Backend (web_fixed.py)
- Motor speed variables now store signed values (-255 to 255)
- Updated `/tank_command` handler to preserve signed FR and LR values
- `/get_motor_speeds` endpoint returns signed motor speeds

### 2. Frontend (index_fixed.html)
- Motor speed display shows signed values with range indicator [-255 to 255]
- Progress bars are bidirectional with:
  - Center line marking the zero point
  - Bars extend left (red) for negative values
  - Bars extend right (green) for positive values
- Wider progress bars (200px) for better visualization

### 3. JavaScript Updates
- Handles signed motor values correctly
- Dynamic color coding based on speed direction:
  - Positive speeds: Green bars extending right from center
  - Negative speeds: Red bars extending left from center
  - Zero speed: No bar visible

## Visual Examples

### Forward Motion (both motors positive):
```
Motor M1: 128    [------------|████████████] [-255 to 255]
Motor M2: 128    [------------|████████████] [-255 to 255]
```
(Green bars extending right)

### Backward Motion (both motors negative):
```
Motor M1: -128   [████████████|------------] [-255 to 255]
Motor M2: -128   [████████████|------------] [-255 to 255]
```
(Red bars extending left)

### Turning (opposite motor directions):
```
Motor M1: 128    [------------|████████████] [-255 to 255]
Motor M2: -128   [████████████|------------] [-255 to 255]
```
(M1 green right, M2 red left)

## Testing
Run the web server:
```bash
python3 web_fixed.py
```

Then either:
1. Use the joystick controls in the web interface
2. Run the test script: `python3 test_motor_speeds.py`

The test script demonstrates various motor states including forward, backward, turning, and stop conditions.
