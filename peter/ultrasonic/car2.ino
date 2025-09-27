// Arduino Code for Tank Control via Serial UART (115200 Baud)
// Connect Raspberry Pi TX (GPIO 14) to Arduino RX (Pin 0)
// Connect Raspberry Pi RX (GPIO 15) to Arduino TX (Pin 1)
// Connect GND of Pi and Arduino

// --- Motor Pins ---
const int in1Pin = 7; // Motor 1 (Left Wheel)
const int in2Pin = 6; 
const int in3Pin = 5; // Motor 2 (Right Wheel)
const int in4Pin = 4; 

// --- Ultrasonic Sensor Pins ---
const int trigPin = 2; // Trigger Pin
const int echoPin = 3; // Echo Pin

// --- Global Variables ---
volatile char current_command = 'X'; 
long last_distance_time = 0;
const int distance_interval = 100; // Send distance data every 100 milliseconds

void setup() {
  Serial.begin(115200); 
  
  // Motor Setup
  pinMode(in1Pin, OUTPUT);
  pinMode(in2Pin, OUTPUT);
  pinMode(in3Pin, OUTPUT);
  pinMode(in4Pin, OUTPUT);
  
  // Ultrasonic Setup
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  digitalWrite(trigPin, LOW); // Ensure Trig is low initially
  
  stopMotors(); 
  Serial.println("Arduino Tank Control & Sensor Ready.");
}

// --- Sensor Function ---

long readDistance() {
  // Clear the trigger pin
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  
  // Set the trigger pin high for 10 microseconds
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  
  // Reads the echo pin, returns the sound wave travel time in microseconds
  long duration = pulseIn(echoPin, HIGH);
  
  // Calculate the distance (cm)
  // Distance = (Duration * Speed of Sound) / 2
  // Speed of Sound in Air is approx. 0.0343 cm/us
  long distance_cm = duration * 0.034 / 2;
  
  return distance_cm;
}

// --- Motor Control Functions (Same as before) ---

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

void turnL() { // A - Spin Left
  digitalWrite(in1Pin, LOW);
  digitalWrite(in2Pin, HIGH);
  digitalWrite(in3Pin, HIGH);
  digitalWrite(in4Pin, LOW);
}

void turnR() { // D - Spin Right
  digitalWrite(in1Pin, HIGH);
  digitalWrite(in2Pin, LOW);
  digitalWrite(in3Pin, LOW);
  digitalWrite(in4Pin, HIGH);
}

// --- Main Loop: Read and Execute ---

void loop() {
  // 1. RECEIVE Serial Data (Motor Commands)
  if (Serial.available()) {
    char incomingChar = Serial.read();
    
    if (incomingChar == 'W' || incomingChar == 'A' || incomingChar == 'S' || incomingChar == 'D' || incomingChar == 'X') {
      current_command = incomingChar;
    }
    // Note: Python must also listen for sensor data from Arduino TX (Pin 1)
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
    case 'X': 
    default: 
      stopMotors();
      break;
  }
  
  // 3. SEND Sensor Data (Non-blocking)
  if (millis() - last_distance_time >= distance_interval) {
    long distance = readDistance();
    // Send data in a clearly parsable format: "Dist:XXX"
    Serial.print("Dist:"); 
    Serial.println(distance); // Use println to add newline for Python parsing
    last_distance_time = millis();
  }
  
  delay(5); // Small delay to keep the loop stable
}
