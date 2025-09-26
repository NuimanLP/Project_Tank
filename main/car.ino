// Arduino Code for Tank Control via Serial UART (115200 Baud)
// Connect Raspberry Pi TX (GPIO 14) to Arduino RX (Pin 0)
// Connect Raspberry Pi RX (GPIO 15) to Arduino TX (Pin 1)
// Connect GND of Pi and Arduino

// Motor 1 (Left Wheel) - Connected to L298N In1 & In2
const int in1Pin = 7; 
const int in2Pin = 6; 
// Motor 2 (Right Wheel) - Connected to L298N In3 & In4
const int in3Pin = 5; 
const int in4Pin = 4; 

// Global variable to hold the last command received
volatile char current_command = 'X'; 

void setup() {
  // Baudrate must match Python's 115200
  Serial.begin(115200); 
  
  // Set all motor pins as OUTPUT
  pinMode(in1Pin, OUTPUT);
  pinMode(in2Pin, OUTPUT);
  pinMode(in3Pin, OUTPUT);
  pinMode(in4Pin, OUTPUT);
  
  stopMotors(); // Start in a stopped state
  Serial.println("Arduino Tank Control Ready. Send W, A, S, D, or X.");
}

// --- Motor Control Functions ---

void stopMotors() {
  digitalWrite(in1Pin, LOW);
  digitalWrite(in2Pin, LOW);
  digitalWrite(in3Pin, LOW);
  digitalWrite(in4Pin, LOW);
}

void fw() { // W - Forward
  digitalWrite(in1Pin, HIGH); 
  digitalWrite(in2Pin, LOW);
  digitalWrite(in3Pin, HIGH);
  digitalWrite(in4Pin, LOW);
}

void re() { // S - Reverse
  digitalWrite(in1Pin, LOW);
  digitalWrite(in2Pin, HIGH);
  digitalWrite(in3Pin, LOW);
  digitalWrite(in4Pin, HIGH);
}

void turnL() { // A - Spin Left (Left wheel reverse, Right wheel forward)
  digitalWrite(in1Pin, LOW);
  digitalWrite(in2Pin, HIGH);
  digitalWrite(in3Pin, HIGH);
  digitalWrite(in4Pin, LOW);
}

void turnR() { // D - Spin Right (Left wheel forward, Right wheel reverse)
  digitalWrite(in1Pin, HIGH);
  digitalWrite(in2Pin, LOW);
  digitalWrite(in3Pin, LOW);
  digitalWrite(in4Pin, HIGH);
}

// --- Main Loop: Read and Execute ---

void loop() {
  // 1. RECEIVE Serial Data
  if (Serial.available()) {
    char incomingChar = Serial.read();
    
    // Process a new command only if it's a known command
    if (incomingChar == 'W' || incomingChar == 'A' || incomingChar == 'S' || incomingChar == 'D' || incomingChar == 'X') {
      // Store the received command
      current_command = incomingChar;
    }
    // Note: Removed Serial.print/println inside loop to maximize responsiveness.
  }

  // 2. EXECUTE the current command continuously
  switch (current_command) {
    case 'W':
      fw();
      break;
    case 'S':
      re();
      break;
    case 'A':
      turnL();
      break;
    case 'D':
      turnR();
      break;
    case 'X': // Use 'X' for explicit stop
    default: 
      stopMotors();
      break;
  }
  
  // A small delay to keep the loop from running too fast, 
  // 5ms ensures that motor commands are re-executed quickly.
  delay(5);
}
