#include <Stepper.h>

// ------------------------------------
// --- DC Motor Pins (สำหรับล้อรถ) ---
// ------------------------------------
const int in1Pin = 7; // Motor 1 (Left Wheel)
const int in2Pin = 6;
const int in3Pin = 5; // Motor 2 (Right Wheel)
const int in4Pin = 4; 

// ---------------------------------------
// --- Step Motor Pins (สำหรับป้อมปืน) ---
// ---------------------------------------
// การต่อสาย: 8->IN1, 9->IN2, 10->IN3, 11->IN4
const int stepsPerRevolution = 2048;      // 28BYJ-48 Steps/Revolution
const int stepsToTake = 50;               // จำนวน Step ที่หมุนต่อการกด 'j' หรือ 'k'
const int stepIn1 = 8; 
const int stepIn2 = 9;
const int stepIn3 = 10;
const int stepIn4 = 11;

// Object Stepper Motor (ใช้ลำดับขาที่ถูกต้องสำหรับ 28BYJ-48: IN1, IN3, IN2, IN4 -> 8, 10, 9, 11)
Stepper myStepper(stepsPerRevolution, stepIn1, stepIn3, stepIn2, stepIn4); 

// ---------------------------------------
// --- Ultrasonic Sensor Pins (คงเดิม) ---
// ---------------------------------------
const int trigPin = 2; // Trigger Pin
const int echoPin = 3; // Echo Pin

// ---------------------------------
// --- Global Variables & Config ---
// ---------------------------------
volatile char current_command = 'X';      // สถานะคำสั่ง DC Motor ล่าสุด (W, A, S, D, X)
long last_distance_time = 0;
const int distance_interval = 100;        // ส่งค่า Sensor ทุก 100 ms

void setup() {
  Serial.begin(115200); // ใช้ Baud Rate 115200 ตาม Code 2
  
  // 1. DC Motor Setup
  pinMode(in1Pin, OUTPUT);
  pinMode(in2Pin, OUTPUT);
  pinMode(in3Pin, OUTPUT);
  pinMode(in4Pin, OUTPUT);

  // 2. Stepper Motor Setup
  myStepper.setSpeed(15); // กำหนดความเร็วรอบต่อนาที (RPM) 
  
  // 3. Ultrasonic Setup
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  digitalWrite(trigPin, LOW); 
  
  stopMotors(); 
  Serial.println("Combined Control Ready.");
  Serial.println("DC Motors: W/A/S/D/X");
  Serial.println("Stepper: 'j' (Left), 'k' (Right) - Steps: " + String(stepsToTake));
}

// ------------------------------------
// --- Sensor & DC Motor Functions ---
// ------------------------------------

long readDistance() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  
  long duration = pulseIn(echoPin, HIGH);
  long distance_cm = duration * 0.034 / 2;
  return distance_cm;
}

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


// ------------------------------------
// --- Main Loop: Read and Execute ---
// ------------------------------------

void loop() {
  // 1. RECEIVE Serial Data
  if (Serial.available()) {
    char incomingChar = Serial.read();
    
    // A. Check for DC Motor commands (W, A, S, D, X)
    if (incomingChar == 'W' || incomingChar == 'A' || incomingChar == 'S' || incomingChar == 'D' || incomingChar == 'X') {
      current_command = incomingChar;
    } 
    // B. Check for Stepper Motor commands (j, k)
    else if (incomingChar == 'j') {
      // คำสั่ง 'j' หมุนซ้าย (ทวนเข็มนาฬิกา) จำนวน 50 steps
      myStepper.step(-stepsToTake); 
    } 
    else if (incomingChar == 'k') {
      // คำสั่ง 'k' หมุนขวา (ตามเข็มนาฬิกา) จำนวน 50 steps
      myStepper.step(stepsToTake); 
    }
    // หมายเหตุ: โค้ดนี้ตัดส่วนการรับค่า Stepper แบบตัวเลข ('P' ตามด้วยตัวเลข) ออกไป
    // เพื่อให้ทำงานแบบง่ายด้วย 'j' และ 'k' เท่านั้น
  }

  // 2. EXECUTE the current command continuously (DC Motors)
  switch (current_command) {
    case 'W': fw(); break;
    case 'S': re(); break;
    case 'A': turnL(); break;
    case 'D': turnR(); break;
    case 'X': 
    default: stopMotors(); break;
  }
  
  // 3. SEND Sensor Data (Non-blocking)
  if (millis() - last_distance_time >= distance_interval) {
    long distance = readDistance();
    Serial.print("Dist:"); 
    Serial.println(distance); 
    last_distance_time = millis();
  }
  
  delay(5); // หน่วงเวลาเล็กน้อยเพื่อให้ลูปทำงานได้อย่างเสถียร
}
