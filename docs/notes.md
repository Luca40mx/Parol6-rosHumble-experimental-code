# Notes and things worth remembering

Personal cheat sheet for this workspace: Ubuntu 22.04, ROS 2 Humble,
VS Code, PlatformIO, Arduino Mega 2560.

---

## VS Code

- **ROS and firmware in one window:** `File > Add Folder to Workspace`, then add
  `firmware/`. PlatformIO only looks for `platformio.ini` in a workspace root,
  so without this its status-bar icons do not appear when the open folder is
  `robot_ws`. The alternative is a second window opened on `firmware/`.
- **C++ IntelliSense for ROS** comes from `.vscode/c_cpp_properties.json`:
  `compilerPath` fixes "cannot open source file cstddef" and
  `/opt/ros/humble/include/**` fixes `rclcpp/rclcpp.hpp`.
- Squiggles that will not go away: `Ctrl+Shift+P` > `Developer: Reload Window`.
- **Do not press the CMake Tools Build button.** It builds `test_node_cpp` as a
  standalone CMake project into its own folder, which `ros2 run` never uses.
  Build only with `colcon build`.
- `.vscode/settings.json` holds absolute paths, so it is git-ignored.
  `c_cpp_properties.json` is portable and is committed.

---

## Workspace and colcon

- Always build from the workspace **root**, never from `src/`.
- `source install/setup.bash` is only needed in terminals opened *before* the
  build. New terminals get it from `~/.bashrc`.
- `build/`, `install/` and `log/` are generated. Never commit them.
  Deleting them is always safe: `rm -rf build install log && colcon build`.
- **colcon scans the whole workspace root**, not just `src/`. To make it skip a
  folder, drop an empty `COLCON_IGNORE` file in it. That is how `firmware/` is
  excluded (colcon itself does the same inside `build/`, `install/` and `log/`).
- `colcon list --names-only` shows which packages colcon can actually see.
- **`--symlink-install`** links files instead of copying them:

  | Changed | Normal build | `--symlink-install` |
  |---|---|---|
  | existing `.py`, `.yaml`, `.launch.py` | rebuild | just restart |
  | `.cpp` | rebuild | rebuild |
  | any **new** file, `setup.py`, `CMakeLists.txt` | rebuild | rebuild |

  Pick one mode and stay with it: mixing them can turn symlinks into copies.
  Switching mode is best done after `rm -rf build install log`.

---

## Parameters and YAML

- A YAML parameter file looks like this, and `/**` means "every node":

  ```yaml
  /**:
    ros__parameters:
      hardware:          # prefix, used to avoid clashes between files
        num_joints: 6
  ```

  The name the node uses is **`prefix.key`**, so `hardware.num_joints`.
  The prefix is the block written *inside* the file, not the file name.
- **`declare_parameter` is what pulls the YAML value into the node.** Without
  it, `get_parameter` raises `ParameterNotDeclaredException` even when the YAML
  provides the value. The default given to `declare_parameter` is used when no
  YAML provides it, and it also **fixes the type**.
- A parameter present in the YAML but **not declared** is silently ignored.
  That is the most common reason a value "does not arrive".
- Write `50.0` and not `50` for a float, or the node fails with a type error.
- If two YAML files define the same name, **the one loaded last wins**, with no
  warning. The launch file loads them in alphabetical order.
- Editing a YAML needs `colcon build`, because the installed file is a copy
  (unless the workspace was built with `--symlink-install`).
- Parameters are flat. Nested YAML becomes dotted names; there are no real
  nested dictionaries as values.
- `automatically_declare_parameters_from_overrides=True` on the Node
  constructor declares everything found in the YAML, but you lose defaults,
  type checking and the explicit list of what the node uses. Not worth it.
- Useful commands:

  ```bash
  ros2 param list /test_node_python
  ros2 param get /test_node_python hardware.num_joints
  ros2 param dump /test_node_python
  ros2 param set /test_node_python hardware.num_joints 4   # runtime, not saved
  ```

### Log level as a number

ROS logging levels are integers, and `set_level` accepts them directly, so no
string-to-enum table is needed in each node:

| debug | info | warn | error | fatal |
|---|---|---|---|---|
| 10 | 20 | 30 | 40 | 50 |

A node prints its messages of that level **and of every more serious level**.
The level applies to the node that sets it, so every new node needs its own
three lines (declare, read, `set_level`).

---

## Launch files

- The function **must** be called `generate_launch_description()`.
- Collecting the YAML files with `glob('*.yaml')` means a new YAML file needs no
  launch edit at all: add the file, `colcon build`, done.
- One `Node(...)` block per node. A new node = copy a block, change `package`
  and `executable`, keep `parameters=param_files`.
- Values only reach the nodes through the launch file (or an explicit
  `--ros-args --params-file`). A plain `ros2 run` sees only the code defaults.
  That is the single most confusing thing about ROS 2 parameters.
- `ros2 launch <pkg> <file> --show-args` lists the arguments a launch accepts.
- A node started by a launch file can still be started alone with `ros2 run`.
- **Launch files including other launch files** (for later):

  ```python
  IncludeLaunchDescription(
      PythonLaunchDescriptionSource(path_to_other_launch_file),
      launch_arguments={'log_level': LaunchConfiguration('log_level')}.items(),
  )
  ```

  Launch arguments are always strings. YAML files do not travel through the
  include: each launch file looks them up again in `robot_config/config`.
- **Circular dependency trap:** if `robot_config` holds both the YAMLs and the
  main launch file, it must depend on every node package, while every node
  package depends on `robot_config` for its YAMLs. colcon refuses that. The
  standard fix is two packages: `robot_config` (YAMLs only, depends on nothing)
  and `robot_bringup` (the main launch, depends on everything).

---

## Running and inspecting nodes

```bash
ros2 run <package> <executable>
ros2 launch robot_config robot_config.launch.py
ros2 node list
ros2 node info /test_node_python
ros2 topic list
ros2 topic echo <topic>
```

- **Node name and executable name are independent.** The executable is what you
  type after `ros2 run` (set in `setup.py` or `CMakeLists.txt`); the node name
  is the string given to the Node constructor and is what `ros2 node list`
  shows. We keep them equal for simplicity.
- `Ctrl+C` stops a node cleanly.
- An empty `ros2 node list` means nothing is running, or the terminals have
  different `ROS_DOMAIN_ID`.
- With `ros2 launch`, a Python node may print
  `process has died ... exit code -2` on `Ctrl+C`. Cosmetic, during shutdown.
- `--no-daemon` on `ros2 node list` avoids leaving a background daemon running.

---

## Firmware and PlatformIO

- Commands, from the `firmware/` folder:

  ```bash
  pio run                   # compile
  pio run --target upload   # compile and flash
  pio device monitor        # serial monitor, Ctrl+C to quit
  pio device list           # which serial ports exist
  ```

  `pio` is on the PATH in VS Code terminals. Elsewhere:
  `~/.platformio/penv/bin/pio`.
- **`monitor_speed` in `platformio.ini` must match `Serial.begin()`** in the
  code, otherwise the monitor shows garbage.
- Libraries are declared in `lib_deps` and downloaded into `.pio/`, which is
  git-ignored. Nothing is installed system-wide and nothing is committed.
- **The Mega 2560 has 8 KB of RAM.** micro-ROS needs several times that and
  does not support AVR at all, so the link to ROS 2 is a plain serial protocol
  plus a bridge node using pyserial. Flash is not the constraint: the demo
  firmware used 4% of flash and 8% of RAM.
- Uploading needs the user in the `dialout` group (already the case here), so
  no `sudo`.
- The board appears as `/dev/ttyACM0` or `/dev/ttyUSB0` depending on the USB
  chip. Nothing appears when it is unplugged.

### Architecture decision: thin firmware, smart host

The Arduino only **reads sensors and drives motors**. Every decision belongs to
ROS 2. The only logic that stays in the firmware is immediate safety, because
serial latency is too high for it:

- stop a motor when its own limit switch triggers;
- stop everything if no command arrives for N milliseconds (watchdog).

Consequences for the code:

- **`loop()` must never block.** No `delay()`, no `while (distanceToGo() != 0)`.
  Each pass: read serial, call `run()` once per motor, send status periodically.
- 9600 baud is too slow for the telemetry of six joints; use 115200.
- Limit switches must block movement **towards** the switch only, otherwise a
  joint resting on its switch can never move away, which breaks homing.

---

## Arm: ROS to Arduino

- **Targets are ABSOLUTE positions, not relative moves.** `data: [0.05, 0, ...]`
  means "go to 0.05 rad". Sending the same command twice moves nothing the
  second time, because the arm is already there.
- **Zero is wherever the arm was when the Arduino powered up**, or wherever it
  last received `zero`. Until the arm has been homed, an angle means nothing in
  absolute robot terms. See *Homing* below.
- Protocol, one command per line. The command words are spelled out rather
  than abbreviated to one letter: at 250000 baud the longest line takes under
  3 ms to send, so there is nothing to save.

  | Direction | Line |
  |---|---|
  | ROS to Arduino | `target_steps <t0..t5>` absolute targets in steps |
  | ROS to Arduino | `halt` stop where you are |
  | ROS to Arduino | `zero` call this position zero |
  | Arduino to ROS | `ok` / `err` |
  | Arduino to ROS | `position_steps <p0..p5>` every 100 ms |
  | Arduino to ROS | `sensors <s0..s5>` every 100 ms, 1 pressed and 0 free |
  | Arduino to ROS | `estop <e>` every 100 ms, 1 while the stop button is held |
  | Arduino to ROS | `blocked <joint> <dir>` a limit switch dropped a target |

  The two step words name what they MEAN, not which way they travel: a target
  is where the arm should go, a position is where it actually is. The direction
  needs no name, because a line is either written or read. Every protocol word
  is lower case, because the firmware compares them letter by letter with
  `strncmp`: one stray capital and the Arduino answers `err` to a command that
  looks correct on screen.

  One word throughout for the six things: **joint**, never motor. "Motor" is
  kept only where it really means the motor as opposed to the joint it drives,
  as in `gear_ratio` and `steps_per_rev`.

  Both lists carry six values in joint order, the same order as the motors.
  The sensors are sent as six separate 0/1 values rather than as a packed
  bitmask: the host publishes them straight onto a topic without decoding.
- `max_abs_rad` per joint in `hardware.yaml` is a **typo guard**, measured from
  the power-on position. It is not a real joint limit. It exists because
  `100` typed instead of `0.1` would otherwise drive the arm into itself.
- PAROL6 joint travels, used as those guards: base 123 deg, shoulder 141.6,
  upperArm 180, elbow 105.5, forearm 90, wrist 360.
- Ratios: base 6.4, shoulder 20, upperArm 18.0952381 (20 x 38/42), elbow 4,
  forearm 4, wrist 10. With 200 pulses/rev on the drivers (full step, no
  microstepping) that gives 203.7 / 636.6 / 576.0 / 127.3 / 127.3 / 318.3
  steps per radian.
- A commanded angle comes back slightly different in `/joint_states`: one step
  of `base` is 0.281 deg, so 0.1 rad becomes 0.0982 rad. That is physical
  quantisation, not a bug. `elbow` and `forearm` are the coarsest, at 0.45
  deg per step.
- **Testing without the robot:** `socat` makes a pair of virtual serial ports,
  and a short Python script can play the part of the firmware. That checks the
  whole chain, conversion included, with the arm switched off.

  ```bash
  socat pty,raw,echo=0,link=/tmp/A pty,raw,echo=0,link=/tmp/B &
  ros2 run arm_bridge arm_bridge --ros-args --params-file <hardware.yaml> \
      -p hardware.port:=/tmp/A
  ```

- Raising `microsteps` gives a finer joint but a slower arm: AccelStepper on a
  16 MHz AVR tops out around 4000 steps/s for one motor, less with six.

## A joint that stops after exactly one step

Symptom: the firmware's step counter advances by 1 and freezes there, in both
directions, while the motor holds position. Everything looks healthy: the
switches all read free when the arm is idle, and the other joints work.

Cause: stepper drivers are electrically noisy. A limit switch wire running
near a pulse line can read LOW for a few microseconds once the motor starts
pulsing, and the old `stepJoint()` believed the first LOW reading it saw. It
then called `moveTo(currentPosition())`, which destroys the target, so the
joint never resumed even after the switch read free again. One step, then
nothing, with no message to explain it.

Two lessons, both already applied to `firmware/src/main.cpp`:

* **Debounce every mechanical input.** A switch counts as pressed only after
  reading LOW without interruption for `DEBOUNCE_MS` (5 ms). Noise is far
  shorter than that, a real press far longer. The cost is a 5 ms late
  detection, about 2 steps of overtravel at 400 steps/s.
* **Never drop a command silently.** The firmware now sends `b <joint> <dir>`
  whenever a limit switch makes it abandon a target, and `arm_bridge` turns
  that into a ROS warning. The bug was hard to find only because the firmware
  stopped without saying so.

Reading the switches while the arm is idle proves nothing: the noise exists
only while a motor is being pulsed. Tell the two apart by the step counter in
the status line, not by the switch byte:

| Counter | Meaning |
|---|---|
| stops short, `b` line printed | the switch reads pressed, really or from noise |
| stops short, no `b` line | something else; collect the output |
| reaches the target, joint still | the pulse never got to the driver (wiring, wrong pin) |
| reaches the target, joint moves | fine |

A motor you cannot turn by hand has holding torque, which already proves its
power, its enable line and its coil wiring are good. Only the step pulse can
be missing, so there is no point testing the power supply.

## Emergency stop

A normally-closed button between **D28** and GND, read in the firmware and
nowhere else.

- **It belongs in the firmware, and only there.** A stop written in ROS stops
  nothing once the node has crashed, the USB has come loose, or the host is
  busy swapping. The firmware checks the pin on every single pass of `loop()`.
- **Normally closed is the whole point.** With `INPUT_PULLUP` the pin reads LOW
  at rest and HIGH when pressed, which is the opposite way round from the limit
  switches. A wire that breaks or falls off leaves the pin pulled HIGH, which
  reads as PRESSED. A stop button has to fail towards stopping.
- **No target is touched while frozen.** `loop()` simply stops calling
  `stepJoint()`, so every target survives and releasing the button carries on
  from exactly where the arm stood. Commands still arrive while frozen, they
  just do not move anything, so a target sent during the freeze is where the
  arm goes when it comes back.
- **The drivers stay powered**, so the motors keep holding the arm up. Cutting
  their current would "stop the motors" by letting the arm fall over.
- **On release the speed is wiped first.** AccelStepper still believes it is
  running at the speed it had when it froze, and would pick that speed straight
  back up from standstill. A stepper asked to jump from 0 to 400 steps/s slips,
  and a slipped step is a position counter that lies. So `resumeAll()` saves
  each target, zeroes the speed with `setCurrentPosition()`, and hands the
  target back: same destination, fresh acceleration ramp.
- **The stop itself is abrupt, and that can cost steps.** Stopping a joint dead
  from full speed is what a stop button is for, not what is kind to a stepper.
  If the arm was moving quickly when it froze, treat the position as suspect
  and home again.
- **Homing survives a freeze by itself**, with no special case anywhere: it
  creeps from the position it MEASURES, so while the arm is frozen the target
  stops advancing too, and homing simply waits. See *Homing* below.
- `estop <0|1>` goes out with every status line and not only when it changes: a
  bridge that starts up while the button is already held has to find out
  somehow. The bridge prints only the changes, and prints the press as an
  ERROR rather than a warning for one reason: errors come out red, warnings
  come out yellow, and red is what you cannot miss in a scrolling terminal.

## Homing

`ros2 launch robot_config homing.launch.py`, with the bridge already running in
another terminal. One joint at a time, and for each one:

1. creep towards the limit switch until it closes;
2. if `search_rad` goes by with no switch, go back to exactly where the joint
   started and look the OTHER way;
3. step back `home_offset_rad` off the switch and stay there.

When the last joint is done, every joint is standing on its home position, so
ONE `zero` turns that whole pose into `0 0 0 0 0 0`. That is the moment
`max_abs_rad` in `hardware.yaml` stops being a typo guard and becomes a real
joint limit.

- **The node never sends a big move.** Every target is `where the joint really
  is` + `step_rad`, read back from `/robot/joint_states`. So the target can
  never get more than one step ahead of the arm: the arm sets the pace, and
  Ctrl-C leaves at most one `step_rad` of travel still commanded.
- **`step_rad` has to be wider than one motor step**, or the bridge rounds it
  to zero steps and the joint stands still for ever with no error at all. The
  widest step is the base's: `2*pi/(200*6.4)` = 0.0049 rad.
- **`home_dir` is only a hint.** It says which way to look FIRST. A wrong
  guess costs a trip out and back, nothing else, so the arm does not have to
  be switched off in any particular pose. Getting it right is worth real time
  though: 2 rad the wrong way on the upperArm is about 25 s, because a 18:1
  joint creeps at roughly 0.165 rad/s.
- **Two travel limits, whichever comes first**: `search_rad` from where the
  joint started, and the `max_abs_rad` guard. Both ways empty is an error:
  `halt`, and nothing zeroed.
- **The `max_abs_rad` check is not optional, it is a deadlock fix.** The bridge
  REFUSES a target past the guard instead of trimming it, so a joint that
  walks into its guard simply stops, and `search_rad` is then never reached
  because the position never changes again: the search waits for ever with the
  bridge logging a refusal ten times a second. That really happened with
  `search_rad: 2.0` on an elbow guarded at 1.84. Homing now stops at the guard
  and turns around, and trims its own targets so the bridge never refuses one.
- **Before homing, `max_abs_rad` is measured from the power-on position**, so
  it can still cut a search short: switch the arm off with a joint far from
  its switch and the guard window may not reach the switch at all. This is a
  bootstrap problem only. After homing the guard is centred on the real zero
  and means what it says. If it keeps cutting homing short, that value is too
  tight for the job it does before homing.
- **The way back is one absolute target, at normal speed**, not a creep. It is
  retracing ground it has just covered, so there is nothing new to run into.
- **Home one joint at a time until every `home_dir` is confirmed**, with
  `homing.joints` in `homing.yaml`. The wrist is the safest one to be wrong
  about: it only spins on itself.
- Accuracy is about 0.005 rad (0.3 deg) with `step_rad: 0.02`, because the
  switch state only arrives every 100 ms. Lower `step_rad` for a slower, more
  repeatable homing.

### What to leave running

- **The bridge runs all the time.** It is the only thing holding the serial
  port, and opening that port resets the Arduino.
- **Homing runs once per bridge session**, for the same reason: a bridge
  restart resets the board and throws the zero away.
- **Leave the homing node running anyway, but not because it is working.**
  After `Ready.` its timer returns on the first line and it does nothing at
  all. What it still does is HOLD `/robot/homed`: `transient_local` keeps the
  last value inside the PUBLISHER, and the publisher is the node. Shut the node
  down and the topic does not go stale, it disappears:

      >>> homing node running:  array('B', [0, 0, 0, 0, 0, 1])
      >>> homing node killed:   Unknown topic '/robot/homed'

  So if anything is ever going to ask "is this arm calibrated", that node has
  to stay alive. If nothing asks, Ctrl-C is harmless.

### The start pose

A home position sits `home_offset_rad` off a limit switch, which is the worst
place to leave an arm parked: every joint is right next to its own end of
travel. So homing ends by walking the arm to `homing.start_pose_rad`.

- **You measure the pose, you do not guess it.** Home the arm, jog it where
  you want it to wait, read the six numbers back, write them down:

      ros2 topic pub --once /robot/target_rad \
        std_msgs/Float64MultiArray "{data: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}"
      ros2 topic echo /robot/joint_states --once --field position

- **All zeros means the home pose**, so the arm does not move. That is the
  default, and it is what happens until the numbers are filled in.
- **One joint at a time.** Nothing in this stack checks collisions or knows
  what is on the desk, so six joints moving at once is a hope, not a plan.
- **A pose is a bad choice if** it is outside a joint's `max_abs_rad` (it gets
  trimmed), or near a limit switch (the firmware refuses one direction of a
  joint whose switch is pressed, so the arm would start out crippled), or
  cannot be REACHED from the home pose without hitting something.

#### Why the node forgets the position right after `zero`

`finish()` sets `self.position = None` the moment it sends `zero`, and that one
line is load-bearing. `zero` moves the whole coordinate frame out from under
the node, but `self.position` still holds the pre-zero numbers for another
tenth of a second, until the next `position_steps` line arrives. A target built
from those asks every joint for its OLD angle measured from the NEW zero, so
the arm lurches by its own home offsets the instant it finishes homing. Dropping
the position makes the guard at the top of `on_timer` wait for fresh numbers.

Measured, with three joints homed and a start pose of `[0.2, 0, 0, 0.3, 0, 0.1]`:

    before zero   [-83, 0, 0, -52, 0, -127]    steps, standing on the switches
    after zero    [  0, 0, 0,   0, 0,    0]    no lurch
                  [ 41, 0, 0,   0, 0,    0]    base alone
                  [ 41, 0, 0,  38, 0,    0]    elbow alone
                  [ 41, 0, 0,  38, 0,   32]    wrist alone, done

### Where the calibration is kept

Three different things, and only one of them is a file.

| What | Where | Survives a reset? |
|---|---|---|
| `home_dir`, `home_offset_rad` | `hardware.yaml` | yes, it is a file |
| The zero itself | the Arduino's RAM, in AccelStepper | **no** |
| Which joints are calibrated now | `/robot/homed`, six 0/1 values | **no**, republished by homing |

- **`hardware.yaml` is the real result of a homing session.** Finding out that
  the wrist's switch is towards `+1` is a permanent fact about the arm, and
  writing it down is what makes the next homing repeatable. Everything else is
  thrown away constantly.
- **The zero lives in the Arduino and dies with it.** `zero` sets
  AccelStepper's step counters to 0. That is RAM. It is lost on a power cycle,
  on the reset button, and **on opening the serial port**: DTR is wired to
  RESET on the Mega, which is how auto-upload works. So restarting the bridge
  loses the homing, and the arm has to be homed again.
- **Do not try to save the zero to a file.** A stepper has no idea where it is:
  it only counts the pulses it was told to send. After a power cycle the arm
  may have been moved by hand, by gravity, or by a missed step, and a saved
  number would be a confident lie. Homing takes a few seconds; guessing is
  permanent. This is the whole reason homing exists.
- **`/robot/homed` is per joint on purpose.** `zero` zeroes all six at once,
  but a joint that was not homed is only being zeroed wherever it happened to
  be standing. After homing the wrist alone it reads `[0, 0, 0, 0, 0, 1]`.
- It is published `transient_local`, so a node started later still gets the
  last value instead of waiting for the next one. `ros2 topic echo` matches
  that by itself:

      ros2 topic echo /robot/homed --field data

### A switch that is already pressed when the arm powers up

The firmware refuses the direction that was being travelled **at the moment a
switch closes**. It can only latch that on the CLOSING EDGE, and here is why:
a switch that was already closed before any target arrived says nothing about
which side of the joint it is on. Blaming whichever direction is asked for
first would lock the joint on top of its own switch, because the only
direction that could free it is the one just refused. That really happened:
homing deadlocked on `upperArm`, which sits on its switch at power-up.

Which side a switch is on is known in ROS, in `home_dir`, not in the firmware.

## Git

- The repo is `Luca40mx/Parol6-rosHumble-experimental-code`, public, Apache-2.0.
- `user.email` is set **per repo** to the GitHub no-reply address, so commits do
  not expose the personal address while the global config keeps it:

  ```bash
  git config user.email "145957795+Luca40mx@users.noreply.github.com"
  ```

- To start a history over with a single first commit (no parent, nothing to
  trace back to):

  ```bash
  git checkout --orphan clean-main && git add -A && git commit -m "..." \
    && git branch -M main
  ```

  Purge what is left locally with
  `git reflog expire --expire=now --all && git gc --prune=now`.
- **A force-push does not really hide a commit:** GitHub can still serve the old
  SHA by direct URL. To be sure, delete and recreate the repository.
- **`.gitignore` anchoring:** a pattern containing a slash anywhere but at the
  end is relative to the file's own folder. `.vscode/*` in the root therefore
  does *not* match `firmware/.vscode/`, which is why `firmware/` has its own
  `.gitignore`.
- Debug an ignore rule with `git check-ignore -v <path>`: it prints the file and
  line that matched.
- Keep big binaries out: a single 22 MB video stays in the history forever, even
  if deleted later.

---

## ros2 run and --ros-args

`ros2 run` splits the command line in two halves:

```bash
ros2 run pkg exe  [args for YOUR program]  --ros-args  [args for ROS]
```

Everything ROS-related goes AFTER `--ros-args`: `--params-file`, `-p name:=value`,
`-r old:=new`, `--log-level`. Put it before and ROS never sees it, the node falls
back to every `declare_parameter` default, and **nothing warns you**:

```bash
ros2 run arm_bridge arm_bridge --params-file hardware.yaml              # IGNORED
ros2 run arm_bridge arm_bridge --ros-args --params-file hardware.yaml   # correct
```

How to spot it: the node logs the defaults from the code instead of the YAML
values. The bridge prints `1.0 ratio` instead of `6.4 ratio`.

A launch file cannot make this mistake, so prefer it:

```bash
ros2 launch robot_config robot_config.launch.py
```

## Serial port names move

`/dev/ttyACM0` and `/dev/ttyACM1` are handed out in the order devices appear, so
they swap between reboots and replugs. The by-id link is tied to the board's
serial number and never moves:

```bash
ls /dev/serial/by-id/
# usb-Arduino__www.arduino.cc__0042_145323032323511132F0-if00 -> ../../ttyACM1
```

That full path is what `hardware.port` holds. It changes only if the Arduino
itself is replaced.

## A new package is not found until you source again

```
package 'xxx' not found, searching: ['.../install/robot_config', ...]
```

That list is not computed when the error happens: it is `AMENT_PREFIX_PATH`,
written into the shell the moment `source install/setup.bash` ran. A package
created afterwards is missing from it, and `colcon build` does not update the
variable in a terminal that is already open.

So a NEW package always takes two steps, in the same terminal:

```bash
colcon build --packages-select <pkg>
source install/setup.bash
```

The same applies to a new `console_scripts` entry in `setup.py`: it creates a
new file in `install/`, so `--symlink-install` does not help. Editing the
CONTENTS of an already-installed Python file is what symlink-install makes
instant.

Check what the launch file will actually find:

```bash
ros2 pkg prefix <pkg>            # where it was installed, or an error
ros2 pkg executables <pkg>       # the names a launch file can use
```

## Silent failures to suspect first

| Symptom | Most likely cause |
|---|---|
| Node prints the default, not the YAML value | `--params-file` put before `--ros-args`, or `colcon build` not run |
| `could not open port /dev/ttyACM0` | the YAML was ignored (see the row above), or the board moved to `ttyACM1` |
| `Parameter not set` | not declared in the node, or a typo in `prefix.key` |
| `Package '...' not found` | not built yet, or not sourced again since it was created |
| Code change has no effect | not rebuilt, or sourced in a stale terminal |
| `Wrong parameter type` | `50` in YAML against a `0.0` default |
| Serial monitor shows garbage | `monitor_speed` differs from `Serial.begin()` |
| Two YAMLs, one value ignored | same parameter name, the later file wins |
| Homing says nothing and nothing moves | the bridge is not running, so no `/robot/joint_states` |
| A joint goes out and comes back before homing | `home_dir` guessed wrong; harmless, just slow |
| Homing fails after looking both ways | that limit switch is not closing at all: check `/robot/sensor_states` |
| Homing hangs and the bridge spams `Refusing target` | a target past `max_abs_rad`; the joint stops but the search keeps waiting |
| Nothing moves, no error anywhere | the emergency button is held, or its wire is broken: both read as pressed |
| Position is wrong after a stop button press | steps slipped in the abrupt stop; home again |
| A joint does not move at all during homing | `step_rad` narrower than one motor step, so it rounds to 0 |
| Two nodes fight over the arm | two publishers on `/robot/target_rad`; a killed `ros2 run` leaves its node alive |
| The arm was homed and now 0 rad is wrong again | the bridge was restarted, which resets the Arduino over DTR |
