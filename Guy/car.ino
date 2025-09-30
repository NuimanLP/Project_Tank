#include <Stepper.h>

// ----------------------------------------------------
// --- กำหนดขาสำหรับ ESP32 (ใช้ขา GPIO ที่เหมาะสม) ---
// ----------------------------------------------------

// 1. DC Motor Pins (สำหรับล้อรถ - เรียงตามที่คุณต้องการ)
// *หมายเหตุ: การใช้งาน in1, in2, in3, in4 ยังคงอ้างอิงถึง Motor 1 และ Motor 2
const int in1Pin = 27; // Motor 1 (Left Wheel) - เดิม 25
const int in2Pin = 26;
const int in3Pin = 25; // Motor 2 (Right Wheel) - เดิม 27
const int in4Pin = 14; 

// 2. Step Motor Pins (สำหรับป้อมปืน - ใช้ 16, 17, 18, 19)
const int stepIn1 = 16; 
const int stepIn2 = 17;
const int stepIn3 = 18;
const int stepIn4 = 19;

// 3. Ultrasonic Sensor Pins (คงเดิม)
const int trigPin = 32; // Trigger Pin
const int echoPin = 33; // Echo Pin 

// ---------------------------------------
// --- Stepper Motor Config (คงเดิม) ---
// ---------------------------------------
const int stepsPerRevolution = 2048;      
const int stepsToTake = 10;               

// Object Stepper Motor: (stepsPerRevolution, IN1, IN3, IN2, IN4)
// ลำดับขาที่ป้อนให้ Stepper.h คือ: 16, 18, 17, 19
Stepper myStepper(stepsPerRevolution, stepIn1, stepIn3, stepIn2, stepIn4); 

// ---------------------------------
// --- Global Variables & Config ---
// ---------------------------------
volatile char current_command = 'X';     
long last_distance_time = 0;
const int distance_interval = 100;       

void setup() {
  Serial.begin(115200); 
  
  // 1. DC Motor Setup
  pinMode(in1Pin, OUTPUT);
  pinMode(in2Pin, OUTPUT);
  pinMode(in3Pin, OUTPUT);
  pinMode(in4Pin, OUTPUT);

  // 2. Stepper Motor Setup
  myStepper.setSpeed(15); 
  
  // 3. Ultrasonic Setup
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  digitalWrite(trigPin, LOW); 
  
  stopMotors(); 
  Serial.println("Combined Control Ready on ESP32 (Final Pin Config).");
  Serial.println("DC Motors: W/A/S/D/X");
  Serial.println("Stepper: 'j' (Left), 'k' (Right) - Steps: " + String(stepsToTake));
}

// ------------------------------------
// --- Sensor & DC Motor Functions ---
// ------------------------------------
// *หมายเหตุ: ฟังก์ชัน fw(), re(), turnL(), turnR() ถูกปรับให้ใช้ขา DC Motor ใหม่แล้ว

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
  digitalWrite(in1Pin, LOW); // 27
  digitalWrite(in2Pin, LOW); // 26
  digitalWrite(in3Pin, LOW); // 25
  digitalWrite(in4Pin, LOW); // 14
}

void fw() { // W - Forward
  digitalWrite(in1Pin, HIGH); // 27
  digitalWrite(in2Pin, LOW);  // 26
  digitalWrite(in3Pin, HIGH); // 25
  digitalWrite(in4Pin, LOW);  // 14
}

void re() { // S - Reverse
  digitalWrite(in1Pin, LOW);  // 27
  digitalWrite(in2Pin, HIGH); // 26
  digitalWrite(in3Pin, LOW);  // 25
  digitalWrite(in4Pin, HIGH); // 14
}

void turnL() { // A - Spin Left (Left Reverse, Right Forward)
  digitalWrite(in1Pin, LOW);  // 27
  digitalWrite(in2Pin, HIGH); // 26
  digitalWrite(in3Pin, HIGH); // 25
  digitalWrite(in4Pin, LOW);  // 14
}

void turnR() { // D - Spin Right (Left Forward, Right Reverse)
  digitalWrite(in1Pin, HIGH); // 27
  digitalWrite(in2Pin, LOW);  // 26
  digitalWrite(in3Pin, LOW);  // 25
  digitalWrite(in4Pin, HIGH); // 14
}

void stopTurret() {
  digitalWrite(stepIn1, LOW); 
  digitalWrite(stepIn2, LOW);
  digitalWrite(stepIn3, LOW); 
  digitalWrite(stepIn4, LOW); 
}


// ------------------------------------
// --- Main Loop: Read and Execute ---
// ------------------------------------

void loop() {
  // 1. RECEIVE Serial Data
  if (Serial.available()) {
    char incomingChar = Serial.read();
    
    // A. Check for DC Motor commands 
    if (incomingChar == 'W' || incomingChar == 'A' || incomingChar == 'S' || incomingChar == 'D') {
      current_command = incomingChar;
      // เมื่อได้รับคำสั่งเคลื่อนที่ ให้เคลียร์คำสั่งหยุด (X) ออกไปก่อน
      // (ไม่จำเป็นต้องเคลียร์ในโค้ดนี้ เพราะจะเคลียร์ตอนได้รับ X โดยตรง)
    } 
    // B. Check for Stepper Motor commands 
    else if (incomingChar == 'j') {
      myStepper.step(-stepsToTake); 
    } 
    else if (incomingChar == 'k') {
      myStepper.step(stepsToTake); 
    }
    // C. *** คำสั่งหยุด DC Motor (X) ***
    else if (incomingChar == 'X') {
        // *** 🔴 เคลียร์คำสั่งที่ค้างอยู่ใน Serial Buffer ทั้งหมดก่อนหยุด ***
        while (Serial.available()) {
            Serial.read();
        }
        current_command = 'X'; // ตั้งค่าคำสั่งปัจจุบันเป็นหยุด
        stopMotors();          // หยุดมอเตอร์ทันที
    }
    // D. *** คำสั่งหยุด Stepper Motor (T) ***
    else if (incomingChar == 'T') { 
        // *** 🔴 เคลียร์คำสั่งที่ค้างอยู่ใน Serial Buffer ทั้งหมดก่อนหยุด ***
        while (Serial.available()) {
            Serial.read(); 
        }
        stopTurret();
    }
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
  
  // delay(5); 
}
