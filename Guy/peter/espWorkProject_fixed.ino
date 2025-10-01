#include <Stepper.h>
#include <ESP32Servo.h>

int forwardReverse = 0;   // FR (Tank Movement)
int leftRight = 0;        // LR (Tank Steering)
int upDown = 0;           // UD (e.g., Camera or Arm Up/Down)
int turretLeftRight = 0;  // TLR (e.g., Turret Rotation)
int fireCannon = 0;
int lightControl = 0;

const int in1Pin = 27;  // H-Bridge input pins
const int in2Pin = 26;
const int in3Pin = 25;  // H-Bridge pins for second motor
const int in4Pin = 14;

// 2. Step Motor Pins (สำหรับป้อมปืน - ใช้ 16, 17, 18, 19)
const int stepIn1 = 16;
const int stepIn2 = 17;
const int stepIn3 = 18;
const int stepIn4 = 19;
const int stepsPerRevolution = 2048;
const int stepsToTake = 10;
const int turnSpeed = 5;
Stepper myStepper(stepsPerRevolution, stepIn1, stepIn3, stepIn2, stepIn4);

const int servoPin = 12;
int servoDeg = 90;
Servo servo1;

//armament
const int laserPin = 23;
const int buzzerPin = 5;

// Ultrasonic Sensor Pins
const int trigPin = 32;  // Trigger Pin
const int echoPin = 33;  // Echo Pin

// Light Pin
const int frontLED = 0;
const int rearLED = 2;

// the setup function runs once when you press reset or power the board
void setup() {
  // initialize digital pin 2 as an output.
  // pinMode(2, OUTPUT);
  Serial.begin(115200);
  pinMode(in1Pin, OUTPUT);
  pinMode(in2Pin, OUTPUT);
  pinMode(in3Pin, OUTPUT);
  pinMode(in4Pin, OUTPUT);

  myStepper.setSpeed(turnSpeed);

  servo1.attach(servoPin);

  pinMode(laserPin, OUTPUT);
  pinMode(buzzerPin, OUTPUT);

  // Ultrasonic Setup
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  digitalWrite(trigPin, LOW);

  // Light
  pinMode(frontLED, OUTPUT);
  pinMode(rearLED, OUTPUT);


}

void checkLight() {
  if (lightControl == 1) {
  digitalWrite(frontLED, HIGH);
  digitalWrite(rearLED, HIGH); 
  } else {
    digitalWrite(frontLED, LOW);
    digitalWrite(rearLED, LOW); 
  }
}


long microsecondsToCentimeters(long microseconds) {
  // The speed of sound is 340 m/s or 29 microseconds per centimeter.
  // The ping travels out and back, so to find the distance of the
  // object we take half of the distance travelled.
  return microseconds / 29 / 2;
}

long readDistance() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(5);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH);
  long distance_cm = microsecondsToCentimeters(duration);
  return distance_cm;
}

unsigned long lastFired = millis();
unsigned int reloadDuration = 500;
bool readyFire = true;
bool firing = false;
//Laser on duration
unsigned int laserDuration = 100;
unsigned int buzzDuration = 190;

void checkAndFireCannon() {
  unsigned long currentMillis = millis();
  unsigned long dif = currentMillis - lastFired;
  if (fireCannon == 1) {
    //Trying to fire

    if (dif > reloadDuration) {
      //Ready Fire
      readyFire = true;
      firing = false;
    }
    if (readyFire) {
      readyFire = false;
      firing = true;
      lastFired = millis();
    }

    fireCannon = 0;
  }
  if (firing) {
    if (dif < laserDuration) {
      digitalWrite(laserPin, HIGH);
    } else {
      digitalWrite(laserPin, LOW);
    }
    if (dif < buzzDuration) {
      digitalWrite(buzzerPin, HIGH);
    } else {
      digitalWrite(buzzerPin, LOW);
    }
  } else {
    digitalWrite(laserPin, LOW);
    digitalWrite(buzzerPin, LOW);
  }
}

void setMotorSpeed(int motorNum, int speed) {
  // Ensure speed is within the -255 to 255 range
  int constrainedSpeed = constrain(speed, -255, 255);
  int motorSpeed = abs(constrainedSpeed);
  Serial.print("M");
  Serial.print(motorNum);
  Serial.print(":");
  Serial.println(constrainedSpeed);

  if (motorNum == 1) { // Control Motor 1
    if (constrainedSpeed > 0) { // Forward
      analogWrite(in1Pin, 0);
      analogWrite(in2Pin, motorSpeed);
    } else if (constrainedSpeed < 0) { // Reverse
      analogWrite(in1Pin, motorSpeed);
      analogWrite(in2Pin, 0);
    } else { // Stop
      analogWrite(in1Pin, 0);
      analogWrite(in2Pin, 0);
    }
  } else if (motorNum == 2) { // Control Motor 2
    if (constrainedSpeed > 0) { // Forward
      analogWrite(in3Pin, 0);
      analogWrite(in4Pin, motorSpeed);
    } else if (constrainedSpeed < 0) { // Reverse
      analogWrite(in3Pin, motorSpeed);
      analogWrite(in4Pin, 0);
    } else { // Stop
      analogWrite(in3Pin, 0);
      analogWrite(in4Pin, 0);
    }
  }
}

void updateMotors(int forwardReverse, int leftRight) {
  // 1. Clamp the input values to the allowed range of -7 to 7
  int throttle = constrain(forwardReverse, -7, 7);
  int steer = constrain(leftRight, -7, 7);

  // 2. Map the -7 to 7 range to the analogWrite range of -255 to 255
  //    map() is a standard Arduino function.
  int mappedThrottle = map(throttle, -7, 7, -255, 255);
  int mappedSteer = map(steer, -7, 7, -255, 255);

  // 3. Mix throttle and steer values to get individual motor speeds
  // This mixing algorithm allows for turning while moving forward/backward
  int leftSpeed = mappedThrottle + mappedSteer;
  int rightSpeed = mappedThrottle - mappedSteer;

  // 4. Set the speed for each motor
  // Motor 1 is assumed to be the left motor, Motor 2 is the right motor.
  setMotorSpeed(1, leftSpeed);
  setMotorSpeed(2, rightSpeed);
}

// the loop function runs over and over again forever
void loop() {
  if (Serial.available()) {
    // 1. Read the incoming command string until the Newline character ('\n')
    // NOTE: Serial.readStringUntil() is a blocking function, but it only
    // blocks for the duration of Serial.setTimeout (default is 1000ms).
    String commandString = Serial.readStringUntil('\n');

    // Remove any potential Carriage Return '\r' that might be present
    commandString.trim();

    if (commandString.length() > 0) {
      // Serial.print("Received: ");
      // Serial.println(commandString);

      // 2. Parse the received string
      parseCommand(commandString);

      // 3. Output the results
      // Serial.print("FR: "); Serial.println(forwardReverse);
      // Serial.print("LR: "); Serial.println(leftRight);
      // Serial.print("UD: "); Serial.println(upDown);
      // Serial.print("TLR: "); Serial.println(turretLeftRight);
      // Serial.print("FC: "); Serial.println(fireCannon);
      // Serial.print("LC: "); Serial.println(lightControl);
      // Serial.println("---");
    }

    

    if (upDown > 3) {
      servoDeg += -1;
    } else if (upDown < -3) {
      servoDeg += 1;
    }
    if (turretLeftRight < -3) {
      myStepper.step(stepsToTake);
    } else if (turretLeftRight > 3) {
      myStepper.step(-stepsToTake);
    }

    if (servoDeg > 180) {
      servoDeg = 180;
    } else if (servoDeg < 0) {
      servoDeg = 0;
    }

    
    
  }
  checkLight();
  servo1.write(servoDeg);
  updateMotors(forwardReverse, leftRight);
  checkAndFireCannon();

  long distance = readDistance();
  Serial.print("Dist:");
  Serial.println(distance);
}

void parseCommand(String dataString) {
  // Use dataString.indexOf(';') to find and process each part
  int start = 0;
  int end = 0;

  // Loop through the string, separating by the ';' character
  while (end != -1) {
    end = dataString.indexOf(';', start);

    // Get the current command part (e.g., "FR:5" or "TLR:8")
    String part;
    if (end == -1) {
      // Last command part
      part = dataString.substring(start);
    } else {
      // Intermediate command part
      part = dataString.substring(start, end);
    }

    // Process the part
    int colonIndex = part.indexOf(':');
    if (colonIndex != -1) {
      String key = part.substring(0, colonIndex);        // e.g., "FR"
      String valueStr = part.substring(colonIndex + 1);  // e.g., "5"
      int value = valueStr.toInt();                      // Convert "5" to 5

      // Assign the value based on the key
      if (key.equalsIgnoreCase("FR")) {
        forwardReverse = value;
      } else if (key.equalsIgnoreCase("LR")) {
        leftRight = value;
      } else if (key.equalsIgnoreCase("UD")) {
        upDown = value;
      } else if (key.equalsIgnoreCase("TLR")) {
        turretLeftRight = value;
      } else if (key.equalsIgnoreCase("FC")) {
        // NEW: Assign the Fire Cannon value
        fireCannon = value;
      } else if (key.equalsIgnoreCase("LC")) {
        // NEW: Assign the Fire Cannon value
        lightControl = value;
      } 
      
      else {
        Serial.print("Warning: Unknown command key received: ");
        Serial.println(key);
      }
    }

    // Move 'start' to the position after the current ';' for the next loop iteration
    start = end + 1;
  }
}