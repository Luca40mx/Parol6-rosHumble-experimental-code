# PAROL6 firmware (Arduino Mega 2560)

PlatformIO project for the firmware that drives the six stepper motors and
reads the six limit switches of the arm.

This folder is **not** a ROS 2 package: it is deliberately outside `src/` and
carries a `COLCON_IGNORE` file, so `colcon build` never looks at it.

## Layout

```text
firmware/
├── platformio.ini     # board, framework and library list
├── src/main.cpp       # the firmware itself
├── include/           # own .h header files (empty for now)
├── lib/               # own libraries, one folder each (empty for now)
└── COLCON_IGNORE      # tells colcon to skip this folder
```

`.pio/` holds the build output and the downloaded libraries. It is generated
and git-ignored.

## Commands

Run them from this folder, with the board plugged in over USB.

```bash
pio run                 # compile only
pio run --target upload # compile and flash the board
pio device monitor      # open the serial monitor (Ctrl+C to quit)
pio device list         # show the detected serial ports
```

In VS Code the same actions are the icons in the blue PlatformIO status bar
at the bottom: check mark = build, arrow = upload, plug = monitor.

## Design: thin firmware, smart host

The Arduino only **reads sensors and drives motors**. Every decision - paths,
speeds, kinematics, homing sequences, robot state - belongs to ROS 2, which
sends commands over the USB serial link.

The only logic that stays here is immediate safety, because serial latency is
too high for it:

- stop a motor when its own limit switch triggers;
- stop everything if no command arrives for N milliseconds (watchdog).

micro-ROS is not an option on this board: the ATmega2560 has 8 KB of RAM and
micro-ROS does not support AVR. The link is therefore a plain text protocol
over serial, read by a bridge node on the ROS 2 side.

## Current state

`src/main.cpp` is still the standalone demo: every joint moves forward and
back forever, with no communication. It is the working starting point, kept
unchanged.

What has to change for the ROS 2 link:

1. **`loop()` must never block.** Today it uses `delay()` and
   `while (distanceToGo() != 0)`; while those run, incoming serial commands
   cannot be read. Each pass of the loop should instead read the serial port,
   call `run()` once per motor, and send status periodically.
2. **Raise the baud rate** from 9600 to 115200, and keep `monitor_speed` in
   `platformio.ini` in sync.
3. **Make the limit switches direction-aware.** Right now a pressed switch
   blocks the joint in both directions, so a joint resting on its switch can
   never move away from it, which breaks homing.
