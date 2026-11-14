// PAROL6 arm firmware - Arduino Mega 2560.
//
// The firmware is deliberately dumb: it moves joints to the step positions
// ROS 2 asks for, and reports back where it is. Every decision (paths, speeds,
// kinematics, homing) is made by ROS 2. The only logic here is safety:
// a limit switch stops its own joint.
//
// PROTOCOL  -  one command per line, terminated by '\n'. Commands are whole
// words rather than single letters: at 250000 baud the longest line here takes
// under 3 ms to send, so there is nothing to gain from abbreviating them.
//
// The two step words say what they MEAN, not which way they travel: a target
// is where the arm should go, a position is where it actually is. Direction is
// already obvious from whether a line is written or read. Every word is lower
// case, because the firmware compares them letter by letter: one stray capital
// is a command the Arduino silently answers "err" to.
//
//   in   target_steps <t0..t5>     where to go, absolute, in steps
//   in   halt                     stop where we are
//   in   zero                     call this position zero
//   out  ok                       command accepted
//   out  err                      command not understood
//   out  position_steps <p0..p5>   where we really are, every 100 ms
//   out  sensors <s0..s5>         limit switches, every 100 ms
//   out  estop <e>                emergency button, every 100 ms, 1 = pressed
//   out  blocked <joint> <dir>    a switch stopped a joint
//
// Both outgoing lists carry six values in the joint order below. In "sensors"
// each value is 1 when that limit switch is pressed and 0 when it is not.
//
// Joint order, the same everywhere (firmware, ROS, YAML):
//   0 base   1 shoulder   2 upperArm   3 elbow   4 forearm   5 wrist

#include <Arduino.h>
#include <AccelStepper.h>
#include <string.h>     // strcmp, strncmp: used to recognise the command words

const uint8_t NUM_JOINTS = 6;

// ---------------------------------------------------------------------------
// Pins. The wiring did not change: only the names did, to match the PAROL6
// joint numbering.
//
//   index  name       joint  pulse  dir  limit switch   old name
//   0      base       J1     45     44   34             shoulder
//   1      shoulder   J2     43     42   33             lateralShoulder
//   2      upperArm   J3     41     40   35             upperArm
//   3      elbow      J4     51     52   31             elbow
//   4      forearm    J5     47     46   32             forearm
//   5      wrist      J6     39     38   36             wrist
// ---------------------------------------------------------------------------
AccelStepper joints[NUM_JOINTS] = {
  AccelStepper(AccelStepper::DRIVER, 45, 44),   // 0 base
  AccelStepper(AccelStepper::DRIVER, 43, 42),   // 1 shoulder
  AccelStepper(AccelStepper::DRIVER, 41, 40),   // 2 upperArm
  AccelStepper(AccelStepper::DRIVER, 51, 52),   // 3 elbow
  AccelStepper(AccelStepper::DRIVER, 47, 46),   // 4 forearm
  AccelStepper(AccelStepper::DRIVER, 39, 38),   // 5 wrist
};

const uint8_t LS_PINS[NUM_JOINTS] = {31, 34, 35, 32, 36, 33};

// ---------------------------------------------------------------------------
// Emergency button: normally closed, between D28 and GND.
//
// NORMALLY CLOSED means the pin reads LOW while the button is at rest, and
// HIGH the moment it is pressed. That is the opposite way round from the limit
// switches above, and it is the whole point of wiring a stop button this way:
// a wire that breaks or falls off leaves the pin pulled HIGH, which reads as
// PRESSED. A stop button has to fail towards stopping, never towards moving.
// ---------------------------------------------------------------------------
const uint8_t ESTOP_PIN = 28;

// True while the arm is frozen by the button. Kept as a variable rather than
// read twice, so that what is reported to ROS is exactly what loop() acted on.
bool estopped = false;

// Conservative limits for the first tests. Raise them once the motion is
// proven reliable: with full steps (200 pulses/rev) there is plenty of margin.
const float MAX_SPEED = 400.0;      // steps per second, per joint
const float ACCELERATION = 400.0;   // steps per second squared

// How often the status line is sent.
const unsigned long STATUS_PERIOD_MS = 100;

// Direction currently blocked by a limit switch, per joint:
//   0 = free, +1 = cannot move forward, -1 = cannot move backward.
int8_t blockedDir[NUM_JOINTS] = {0, 0, 0, 0, 0, 0};

// Debouncing of the limit switches. Stepper drivers are electrically noisy,
// and a switch wire running next to a pulse line can read LOW for a few
// microseconds while the motor moves. Believing such a glitch would stop a
// joint that nothing is touching, so a switch counts as pressed only once it
// has read LOW without interruption for DEBOUNCE_MS.
const unsigned long DEBOUNCE_MS = 5;
bool lowSeen[NUM_JOINTS] = {false, false, false, false, false, false};
unsigned long lowSinceMs[NUM_JOINTS] = {0, 0, 0, 0, 0, 0};

// Was each switch pressed on the previous pass of loop()? A switch may only
// block a direction at the moment it CLOSES while the joint is moving: that is
// the moment the joint ran into something, and the direction it was going is
// the dangerous one.
//
// A switch that was ALREADY closed before any target arrived says nothing
// about which side of the joint it is on, and blaming whichever direction we
// happen to be asked for first would lock the joint on top of its own switch
// with no way off it: the one direction that could free it is the one just
// refused. The side a switch is on is known in ROS, not here, and that is
// exactly what homing is for.
bool wasPressed[NUM_JOINTS] = {false, false, false, false, false, false};


// True only for a switch that has been held down long enough to be real.
bool switchPressed(uint8_t i)
{
    if (digitalRead(LS_PINS[i]) != LOW) {
        lowSeen[i] = false;
        return false;
    }
    const unsigned long now = millis();
    if (!lowSeen[i]) {
        // First LOW reading: start the clock, but do not believe it yet.
        lowSeen[i] = true;
        lowSinceMs[i] = now;
        return false;
    }
    return (now - lowSinceMs[i]) >= DEBOUNCE_MS;
}

// Pressed, with no debouncing: this is the one input where a single reading is
// worth believing straight away. A false stop costs a moment, a late stop does
// not. On release a bounce only pauses the arm again for a few milliseconds.
bool estopPressed()
{
    return digitalRead(ESTOP_PIN) == HIGH;
}


// Hand every joint its target back, with its speed reset to zero.
//
// Freezing the arm leaves AccelStepper believing it is still running at
// whatever speed it had, and without this it would pick that speed straight
// back up from standstill the moment the button is released. A stepper asked
// to go from stopped to 400 steps/s in one step does not: it slips, and a
// slipped step is a position counter that quietly lies about where the arm is.
// So the target is saved, the speed is wiped, and the target is given back:
// same destination, fresh acceleration ramp.
void resumeAll()
{
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        const long target = joints[i].targetPosition();
        joints[i].setCurrentPosition(joints[i].currentPosition());
        joints[i].moveTo(target);
    }
}


// Buffer for the line being received.
char buf[80];
uint8_t bufLen = 0;

unsigned long lastStatusMs = 0;


// Stop every joint exactly where it is, by making the target equal to the
// current position.
void haltAll()
{
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        joints[i].moveTo(joints[i].currentPosition());
    }
}


const char CMD_TARGET_STEPS[] = "target_steps";


void handleCommand(char * line)
{
    const uint8_t cmdLen = strlen(CMD_TARGET_STEPS);

    if (strncmp(line, CMD_TARGET_STEPS, cmdLen) == 0) {
        long t[NUM_JOINTS];
        // Read the numbers that follow the command word. sscanf returns how
        // many values it managed to read, and we insist on all six: a short
        // line would otherwise leave some joints with a stale target.
        int n = sscanf(line + cmdLen, "%ld %ld %ld %ld %ld %ld",
                       &t[0], &t[1], &t[2], &t[3], &t[4], &t[5]);
        if (n != NUM_JOINTS) {
            Serial.println(F("err"));
            return;
        }
        for (uint8_t i = 0; i < NUM_JOINTS; i++) {
            joints[i].moveTo(t[i]);
        }
        Serial.println(F("ok"));

    } else if (strcmp(line, "halt") == 0) {
        haltAll();
        Serial.println(F("ok"));

    } else if (strcmp(line, "zero") == 0) {
        // setCurrentPosition() also sets the target to the same value and
        // resets the speed, so the joint stays still.
        for (uint8_t i = 0; i < NUM_JOINTS; i++) {
            joints[i].setCurrentPosition(0);
        }
        Serial.println(F("ok"));

    } else {
        Serial.println(F("err"));
    }
}


// Read whatever arrived, without ever waiting. A command is handled only when
// its closing newline shows up.
void readSerial()
{
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (bufLen > 0) {
                buf[bufLen] = '\0';
                handleCommand(buf);
                bufLen = 0;
            }
        } else if (bufLen < sizeof(buf) - 1) {
            buf[bufLen++] = c;
        }
        // A line longer than the buffer has its extra characters dropped.
    }
}


void sendStatus()
{
    // Where every joint is, in steps.
    Serial.print(F("position_steps"));
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        Serial.print(' ');
        Serial.print(joints[i].currentPosition());
    }
    Serial.println();

    // The limit switches, one 0 or 1 per joint, in the same order. The
    // debounced reading is used, so this matches what stepJoint() acts on
    // rather than showing electrical noise.
    Serial.print(F("sensors"));
    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        Serial.print(' ');
        Serial.print(switchPressed(i) ? 1 : 0);
    }
    Serial.println();

    // The emergency button. Sent every time and not only when it changes: a
    // bridge that starts up while the button is already held down has to find
    // out somehow, and there would be no change left to tell it.
    Serial.print(F("estop "));
    Serial.println(estopped ? 1 : 0);
}


// One joint: respect its limit switch, then take at most one step.
void stepJoint(uint8_t i)
{
    const bool pressed = switchPressed(i);
    const bool justClosed = pressed && !wasPressed[i];
    wasPressed[i] = pressed;

    const long togo = joints[i].distanceToGo();
    const int8_t dir = (togo > 0) ? 1 : ((togo < 0) ? -1 : 0);

    if (!pressed) {
        // Switch released: the joint is free again in both directions.
        blockedDir[i] = 0;
    } else if (justClosed && dir != 0) {
        // Just hit the switch WHILE MOVING: remember which way we were going
        // and refuse that direction from now on. The opposite direction stays
        // allowed, which is what makes homing and backing off possible.
        blockedDir[i] = dir;
        // Say it out loud. Dropping a target silently is impossible to debug
        // from the host: the joint simply stops and nothing explains why.
        Serial.print(F("blocked "));
        Serial.print(i);
        Serial.print(' ');
        Serial.println(dir);
        // Asked to push into the switch: give up on this target, so the arm
        // does not lurch onward the moment the switch is released.
        joints[i].moveTo(joints[i].currentPosition());
        return;
    }

    if (blockedDir[i] != 0 && dir == blockedDir[i]) {
        // Still being asked to push into the switch. Refuse the step, but
        // leave the target alone: it was already dropped above.
        return;
    }

    joints[i].run();
}


void setup()
{
    Serial.begin(250000);

    pinMode(ESTOP_PIN, INPUT_PULLUP);

    for (uint8_t i = 0; i < NUM_JOINTS; i++) {
        pinMode(LS_PINS[i], INPUT_PULLUP);
        joints[i].setMaxSpeed(MAX_SPEED);
        joints[i].setAcceleration(ACCELERATION);
    }
}


void loop()
{
    // Nothing in here is allowed to block: no delay(), no waiting loop.
    // Every pass reads the serial port, moves each joint by at most one step,
    // and sends the status when it is due.
    readSerial();

    // The button is checked before anything that moves. While it is held, no
    // joint is stepped at all, and NO TARGET IS TOUCHED: that is what lets a
    // release carry on from exactly where the arm froze. Commands still arrive
    // while frozen, they just do not move anything until the button comes up.
    //
    // The drivers stay powered the whole time, so the motors keep holding the
    // arm up. Cutting their current would "stop the motors" by letting the arm
    // fall over.
    const bool stop = estopPressed();

    if (stop != estopped) {
        estopped = stop;
        if (!estopped) {
            resumeAll();
        }
    }

    if (!estopped) {
        for (uint8_t i = 0; i < NUM_JOINTS; i++) {
            stepJoint(i);
        }
    }

    const unsigned long now = millis();
    if (now - lastStatusMs >= STATUS_PERIOD_MS) {
        lastStatusMs = now;
        sendStatus();
    }
}
