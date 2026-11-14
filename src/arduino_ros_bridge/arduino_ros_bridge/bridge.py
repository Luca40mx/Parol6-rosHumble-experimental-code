"""Serial bridge between ROS 2 and the Arduino Mega firmware.

listen: /robot/target_rad & /robot/command
publish: /robot/joint_states & /robot/sensor_states

What it does:

  - listens on /robot/target_rad for six joint angles in radians; IN SPECIFIC ORDER! [base, shoulder, upper_arm, elbow, forearm, wrist]
  - listens on /robot/command for a word the firmware already knows, like "zero";
  - turns RAD into step counts and sends one "target_steps ..." line to the Arduino;
  - reads the "position_steps ..." lines coming back and publishes /robot/joint_states;
  - reads the "sensors ..." lines coming back and publishes /robot/sensor_states;
  - reads the "estop ..." lines and shouts, in red, when the button changes.

Every decision belongs to other ROS nodes. This one only translates.
"""

import math
import time

import rclpy
import serial
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray, String, UInt8MultiArray
# pyright: reportArgumentType=false
# pyright: reportUnboundVariable=false

# Joint order. This MUST match the order of the joints[] array in the
# firmware, because the protocol sends six bare numbers with no names.
JOINT_NAMES = ("base", "shoulder", "upperArm", "elbow", "forearm", "wrist")


class ArduinoRosBridge(Node):
    """Translates radians to steps in one direction and back in the other."""

    def __init__(self, node_name: str):
        super().__init__(node_name)

        self.declare_parameter("common.log_level", 20)
        log_level = self.get_parameter("common.log_level").value
        self.get_logger().set_level(log_level)


        self.declare_parameter("hardware.port", "/dev/ttyACM0")
        port = str(self.get_parameter("hardware.port").value)

        self.declare_parameter("hardware.baudrate", 250000)
        baud = int(self.get_parameter("hardware.baudrate").value)


        # One list per value, in joint order. Lists and not single variables:
        # the loop below would overwrite a variable on every turn, and only the
        # last joint would survive.
        self.steps_per_rad = []
        self.sign = []
        self.max_abs_rad = []

        for name in JOINT_NAMES:
            self.declare_parameter(f"hardware.joints.{name}.steps_per_rev", 200)
            spr = int(self.get_parameter(f"hardware.joints.{name}.steps_per_rev").value)

            self.declare_parameter(f"hardware.joints.{name}.microsteps", 1)
            microsteps = int(self.get_parameter(f"hardware.joints.{name}.microsteps").value)

            self.declare_parameter(f"hardware.joints.{name}.gear_ratio", 1.0)
            gear_ratio = float(self.get_parameter(f"hardware.joints.{name}.gear_ratio").value)

            self.declare_parameter(f"hardware.joints.{name}.invert", False) # Set to true when the joint turns the wrong way
            invert = bool(self.get_parameter(f"hardware.joints.{name}.invert").value)

            self.declare_parameter(f"hardware.joints.{name}.max_abs_rad", 1.0) # Typo guard: the widest travel this joint is allowed, **in radians**
            max_abs_rad = float(self.get_parameter(f"hardware.joints.{name}.max_abs_rad").value)

            # steps_per_rad = steps_per_rev * microsteps * gear_ratio / (2*pi)
            self.steps_per_rad.append(spr * microsteps * gear_ratio / (2.0 * math.pi))
            self.sign.append(-1.0 if invert else 1.0) # **sign** turns "invert" into something we can multiply by
            self.max_abs_rad.append(max_abs_rad)

            self.get_logger().debug (f"{name}: {spr} steps/rev x {microsteps} microsteps x {gear_ratio} ratio -> {self.steps_per_rad[-1]:.2f} steps/rad, guard +/-{max_abs_rad} rad")


        self.get_logger().debug(f"Port: {port}, Baudrate: {baud}")


        self.ser = serial.Serial(port, baud, timeout=0.0)
        self.get_logger().debug(f"Serial port {port} opened at {baud} baud.")
        time.sleep(2.0)
        self.ser.reset_input_buffer()
        self.rx=b"" # prepare a sequence of bytes to receive a line from the serial port, ** RX means "receive" **, b indicates "bytes" type
        self.limit_switches = [0] * len(JOINT_NAMES) # last known state of the limit switches, one 0 or 1 per joint
        self.estop = 0 # last known state of the emergency button, 1 while it is held down



        self.joint_state_publisher = self.create_publisher(JointState, '/robot/joint_states', 10)
        self.sensor_states_publisher = self.create_publisher(UInt8MultiArray, '/robot/sensor_states', 10)

        self.target_rad_subscriber = self.create_subscription(Float64MultiArray, '/robot/target_rad', self.rad_to_target_steps, 10)
        self.command_subscriber = self.create_subscription(String, '/robot/command', self.forward_command, 10)

        # 50 Hz, twice as often as the Arduino sends its lines, so the bridge
        # never falls behind. The timer is what makes the node read the serial
        # port: **nothing happens on its own**, ROS has to call us.
        self.timer = self.create_timer(0.02, self.on_timer)


        self.get_logger().info(f"Bridge ready. Listening on {self.target_rad_subscriber.topic_name}, publishing {self.joint_state_publisher.topic_name} and {self.sensor_states_publisher.topic_name}.")



    # ROS -> Arduino

    def rad_to_target_steps(self, msg):
        """Turn six angles in radians into one "target_steps" line."""

        # check if we LISTEN the right number of values, one per joint. From /robot/target_rad
        if len(msg.data) != len(JOINT_NAMES):
            self.get_logger().error(f"Expected {len(JOINT_NAMES)} values, got {len(msg.data)}")
            return

        # Typo guard, one limit per joint. The whole message is refused instead
        # of being clamped: a value this far out is a mistake, not a request.
        for name, rad, limit in zip(JOINT_NAMES, msg.data, self.max_abs_rad):
            if not math.isfinite(rad) or abs(rad) > limit:
                self.get_logger().error(f"Refusing target: {name}={rad} rad is outside its +/-{limit} rad guard (hardware.joints.{name}.max_abs_rad in hardware.yaml). Nothing was sent to the arm.")
                return

        # These are **absolute** targets, not movements: "go to this angle".
        steps = []
        for rad, step_per_rad, sign in zip(msg.data, self.steps_per_rad, self.sign):
            step = round(rad * step_per_rad * sign)
            steps.append(int(step))

        # send to Arduino
        line = "target_steps " + " ".join(str(s) for s in steps)
        self.ser.write((line + "\n").encode())
        self.get_logger().debug(f"Command sent to Arduino from the bridge --> {line}")


    def forward_command(self, msg):
        """Pass one word through to the Arduino, without understanding it.

        For the commands that carry no numbers: "zero" and "halt". Nothing is
        checked here, because the firmware already answers "err" to a word it
        does not know, and handle_line() below prints that as an error.
        """
        line = msg.data.strip()
        if not line:
            return

        self.ser.write((line + "\n").encode())
        self.get_logger().info(f"Command forwarded to Arduino from the bridge --> {line}")



    # Arduino -> ROS

    #Arduino can send these:    position_steps 100 200 300 400 500 600\n
    #                           sensors 0 1 0 0 1 0\n
    #                           estop 0\n
    #                           blocked 1 -1\n
    #                           ok\n
    #                           err\n

    def on_timer(self):
        """Read whatever arrived and handle every line that is complete."""
        data = self.ser.read(4096)
        if not data:
            return

        self.rx = self.rx + data # add new bytes to the end of the bytes already received that are on data

        # We use this while loop to split multiples lines that are read from the Arduino. Until the new byter line is complete, keep reading. Until you see a /n, new line, the line is not complete. if in the byter received there is not a /n, just not enter in the while loop, and wait for the next timer to read more bytes
        while b"\n" in self.rx:
            raw, self.rx = self.rx.split(b"\n", 1) # split the bytes received into two parts: the first part is a complete line, before /n and it's in RAW, the second part is the rest of the bytes that are not yet complete and are on self.rx
            text = raw.decode("ascii", errors="ignore") # convert bytes into string: from arduino: b'sensors 0 1 0 0 1 0' --decode--> 'sensors 0 1 0 0 1 0'
            clean_text = text.strip() # remove white spaces at the beginning and at the end of the string: '  sensors 0 1 0 0 1 0 \r' --strip--> 'sensors 0 1 0 0 1 0'
            self.handle_line(clean_text) # function below to handle the line received from the Arduino. The line is already clean, so no need to clean it again in the function handle_line, it was clean in the 2 lines above


    def handle_line(self, line):
        """Act on one complete line coming from the Arduino."""
        if not line:
            return

        parts = line.split() # if line is line = 'position_steps 100 200 300 400 500 600' --> parts = ['position_steps', '100', '200', '300', '400', '500', '600']

        try:
            if parts[0] == "position_steps" and len(parts) == len(JOINT_NAMES) + 1: # check if the message contains joint steps and has 7 elements. +1 because the first part is the word "position_steps", plus 6 joint values, so joint_names length plus "position_steps"
                self.publish_joint_states([int(p) for p in parts[1:]])
                return

            if parts[0] == "sensors" and len(parts) == len(JOINT_NAMES) + 1:
                self.publish_sensor_states([int(p) for p in parts[1:]])
                return

            if parts[0] == "estop" and len(parts) == 2:
                self.report_estop(int(parts[1]))
                return

            if parts[0] == "blocked" and len(parts) == 3:
                self.report_blocked(int(parts[1]), int(parts[2]))
                return
        except ValueError:
            # The line starts with a word we know but holds something that is
            # not a number. Serial lines do get corrupted, so do not crash.
            self.get_logger().warn(f"Could not read the numbers in: {line}")
            return

        if line == "ok":
            return

        if line == "err":
            self.get_logger().error("Arduino did not understand the last command")
            return

        # Anything else is probably a boot message: show it, do not parse it.
        self.get_logger().info(f"<- {line}")


    def publish_joint_states(self, steps):
        """Steps back into radians: the exact opposite of rad_to_target_steps."""
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg() # **stamp** says when this was true, not when it was published
        msg.name = list(JOINT_NAMES)
        msg.position = [s / step_per_rad * sign for s, step_per_rad, sign in zip(steps, self.steps_per_rad, self.sign)]
        self.joint_state_publisher.publish(msg)


    def publish_sensor_states(self, values):
        """The six limit switches, 1 pressed and 0 free, in joint order."""
        msg = UInt8MultiArray()
        msg.data = values
        self.sensor_states_publisher.publish(msg)

        # Log only what changed. This line arrives ten times a second, so
        # printing it every time would bury every other message.
        if values != self.limit_switches:
            for name, before, now in zip(JOINT_NAMES, self.limit_switches, values):
                if before != now:
                    if now:
                        self.get_logger().warn(f"Limit switch PRESSED on {name}")
                    else:
                        self.get_logger().info(f"Limit switch released on {name}")
            self.limit_switches = values


    def report_estop(self, value):
        """The emergency button. Shout when it changes, keep quiet otherwise.

        This line arrives ten times a second like the other two, so only a
        CHANGE is worth printing. Pressed is logged as an error and not as a
        warning for one reason only: errors come out red, warnings come out
        yellow, and red is what you cannot miss in a terminal that is already
        scrolling.
        """
        if value == self.estop:
            return

        self.estop = value

        if value:
            self.get_logger().error("EMERGENCY STOP PRESSED!")
        else:
            self.get_logger().info("Emergency stop released.")


    def report_blocked(self, joint, direction):
        """The firmware threw a target away because a limit switch was there."""
        name = JOINT_NAMES[joint] if 0 <= joint < len(JOINT_NAMES) else joint
        self.get_logger().info(f"{name}: limit switch blocked direction {direction:+d}, the target was dropped. Send a target the other way to back off.")



    def close(self):
        """Tell the arm to stop, then let go of the port."""
        try:
            self.ser.write(b"halt\n")
            self.ser.flush()
            self.ser.close()
        except Exception as exc:
            self.get_logger().warn(f"Could not close the port cleanly: {exc}")



def main():
    node = None
    rclpy.init()
    try:
        node = ArduinoRosBridge("arduino_ros_bridge_node")
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except serial.SerialException as exc:
        print(f'Serial error: {exc}')
    finally:
        if node is not None:
            node.close()
            node.destroy_node()
        rclpy.try_shutdown()




if __name__ == "__main__":
    main()
