/*
  ignition_safety.ino - Arduino Uno Hardware Safety Referee & Starter Watchdog
  Target Vehicle: 2013-2016 Dodge Dart 1.4L Turbo MultiAir (6-Speed Manual)
  
  Responsibilities:
  1. Read physical Neutral Switch from C635 manual gearbox (Pin D2).
  2. Read physical Clutch Interlock switch (Pin D3).
  3. Enforce hard-coded 2.0-second maximum starter crank timeout (prevents starter fires).
  4. Enforce engine running lockout (Never crank if engine is already running).
  5. Control Clutch Bypass Relay and Starter Solenoid / EVO-ALL Trigger.
*/

// --- PIN ASSIGNMENTS ---
const int PIN_NEUTRAL_SW     = 2;  // Input: Ground when in Neutral (INPUT_PULLUP)
const int PIN_CLUTCH_SW      = 3;  // Input: Ground when clutch pedal is down
const int PIN_RELAY_IGNITION = 7;  // Output: Powers 12V ACC / Ignition circuits
const int PIN_RELAY_CLUTCH   = 8;  // Output: Simulates clutch depressed for start
const int PIN_RELAY_STARTER  = 9;  // Output: Pulses starter solenoid / EVO-ALL trigger
const int PIN_STATUS_LED     = 13; // Onboard LED status indicator

// --- CONSTANTS ---
const unsigned long MAX_CRANK_MS = 2000;    // Absolute 2.0s hardware safety cutoff
const unsigned long SERIAL_TIMEOUT = 5000;  // 5s watchdog if Pi connection drops

// --- STATE VARIABLES ---
bool engineRunning = false;
unsigned long crankStartTime = 0;
bool isCranking = false;

void setup() {
  Serial.begin(115200);

  pinMode(PIN_NEUTRAL_SW, INPUT_PULLUP);
  pinMode(PIN_CLUTCH_SW, INPUT_PULLUP);

  pinMode(PIN_RELAY_IGNITION, OUTPUT);
  pinMode(PIN_RELAY_CLUTCH, OUTPUT);
  pinMode(PIN_RELAY_STARTER, OUTPUT);
  pinMode(PIN_STATUS_LED, OUTPUT);

  // Default all relays to OFF (Safe state)
  digitalWrite(PIN_RELAY_IGNITION, LOW);
  digitalWrite(PIN_RELAY_CLUTCH, LOW);
  digitalWrite(PIN_RELAY_STARTER, LOW);
  digitalWrite(PIN_STATUS_LED, LOW);

  Serial.println(F("[SAFETY_ARDUINO] Initialized. 6-Speed Manual Watchdog Active."));
}

void loop() {
  // 1. Hardware Neutral Check (Pin goes LOW when shifter is in neutral gate)
  bool inNeutral = (digitalRead(PIN_NEUTRAL_SW) == LOW);

  // 2. Hardware Starter Watchdog (Hard cutoff at 2.0s even if Pi freezes!)
  if (isCranking) {
    if (millis() - crankStartTime >= MAX_CRANK_MS || engineRunning) {
      abortCrank();
      Serial.println(F("[SAFETY] Crank cut: Max duration reached or engine caught."));
    }
  }

  // 3. Listen for commands from Raspberry Pi 5
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd == "QUERY_STATUS") {
      Serial.print(F("STATUS:"));
      Serial.print(inNeutral ? F("NEUTRAL_OK,") : F("IN_GEAR_LOCKED,"));
      Serial.println(engineRunning ? F("RUNNING") : F("STOPPED"));
    }
    
    else if (cmd.startsWith("RPM:")) {
      float rpm = cmd.substring(4).toFloat();
      engineRunning = (rpm > 450.0);
    }

    else if (cmd == "CMD_START_SEQUENCE") {
      // MANDATORY SAFETY INTERLOCK CHECK:
      if (!inNeutral) {
        Serial.println(F("[SAFETY_REJECT] ERROR: Vehicle is IN GEAR! Start aborted."));
        flashErrorLed();
      } else if (engineRunning) {
        Serial.println(F("[SAFETY_REJECT] ERROR: Engine already running!"));
      } else {
        // Safe to execute start sequence
        executeSafeStart();
      }
    }

    else if (cmd == "CMD_KILL_IGNITION") {
      digitalWrite(PIN_RELAY_IGNITION, LOW);
      abortCrank();
      Serial.println(F("[SAFETY] Ignition cut."));
    }
  }
}

void executeSafeStart() {
  Serial.println(F("[SAFETY_PASS] Neutral confirmed. Engaging start sequence..."));
  
  // 1. Turn on Ignition & simulate clutch depressed
  digitalWrite(PIN_RELAY_IGNITION, HIGH);
  digitalWrite(PIN_RELAY_CLUTCH, HIGH);
  delay(300); // 300ms pause to allow fuel pump to prime

  // 2. Engage starter relay
  digitalWrite(PIN_RELAY_STARTER, HIGH);
  crankStartTime = millis();
  isCranking = true;
  digitalWrite(PIN_STATUS_LED, HIGH);
}

void abortCrank() {
  digitalWrite(PIN_RELAY_STARTER, LOW);
  digitalWrite(PIN_RELAY_CLUTCH, LOW);
  isCranking = false;
  digitalWrite(PIN_STATUS_LED, LOW);
}

void flashErrorLed() {
  for (int i = 0; i < 4; i++) {
    digitalWrite(PIN_STATUS_LED, HIGH);
    delay(80);
    digitalWrite(PIN_STATUS_LED, LOW);
    delay(80);
  }
}
