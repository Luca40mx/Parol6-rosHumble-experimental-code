"""Homing: find the limit switch of every joint, then call that pose zero.

listen: /robot/joint_states & /robot/sensor_states
publish: /robot/target_rad & /robot/command & /robot/homed

Why this node has to exist:

  The firmware calls "zero" wherever the arm happened to be when it was
  switched on, so 0 rad means nothing at all. The limit switches are the only
  things on the arm that never move: the angle at which a switch closes is
  always the same angle. Homing goes and finds it.

What it does, ONE JOINT AT A TIME:

  - creeps towards the switch until the switch closes;
  - if search_rad goes by with no switch, comes back to exactly where the
    joint started and looks the OTHER way. Only when both ways come up empty
    is it an error, so the arm does not have to be switched off in any
    particular pose;
  - moves home_offset_rad back off the switch and leaves the joint there.

  When the last joint is done, all six are standing on their home positions,
  and a single "zero" turns that whole pose into 0 0 0 0 0 0. Then the arm
  walks to homing.start_pose_rad, one joint at a time, because a home position
  is a few degrees off a limit switch and that is the worst place to leave an
  arm parked.

  Which joints that zero really means something for is published on
  /robot/homed, because it is NOT every joint: "zero" zeroes all six at once,
  but a joint that was not homed is only being zeroed wherever it happened to
  be standing. That is exactly the lie this node refuses to tell.

Only **absolute** targets are ever sent, like from every other node. Each one
is taken from where the joint REALLY is, plus one small step: that is also
what keeps the arm slow, because the arm sets the pace and the target can
never run away from it.
"""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import JointState
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Float64MultiArray, String, UInt8MultiArray
# pyright: reportArgumentType=false

# Joint order. The same tuple as in the bridge, and the same order as the
# joints[] array in the firmware: the protocol sends six bare numbers with no
# names, so everybody has to agree on what the third number means.
JOINT_NAMES = ("base", "shoulder", "upperArm", "elbow", "forearm", "wrist")


class Homing(Node):
    """Looks for the limit switches and turns the pose it stops on into zero."""

    def __init__(self, node_name: str):
        super().__init__(node_name)

        self.declare_parameter("common.log_level", 20)
        log_level = self.get_parameter("common.log_level").value
        self.get_logger().set_level(log_level)


        self.declare_parameter("homing.joints", ["wrist"]) # which joints to home, homed in this order
        wanted = list(self.get_parameter("homing.joints").value)

        self.declare_parameter("homing.search_rad", 1.0) # how far to look EACH WAY before giving up
        self.search_rad = float(self.get_parameter("homing.search_rad").value)

        self.declare_parameter("homing.step_rad", 0.02) # one creep towards the switch
        self.step_rad = float(self.get_parameter("homing.step_rad").value)

        self.declare_parameter("homing.tolerance_rad", 0.01) # close enough to call a move finished
        self.tolerance_rad = float(self.get_parameter("homing.tolerance_rad").value)

        self.declare_parameter("homing.rate_hz", 10.0) # how often a new target is sent
        rate_hz = float(self.get_parameter("homing.rate_hz").value)

        self.declare_parameter("homing.start_pose_rad", [0.0] * len(JOINT_NAMES)) # where to park once homed
        self.start_pose_rad = [float(v) for v in self.get_parameter("homing.start_pose_rad").value]

        if len(self.start_pose_rad) != len(JOINT_NAMES):
            self.get_logger().error(f"homing.start_pose_rad needs {len(JOINT_NAMES)} values, got {len(self.start_pose_rad)}. Staying on the home pose instead.")
            self.start_pose_rad = [0.0] * len(JOINT_NAMES)


        # One list per value, in joint order. Lists and not single variables:
        # the loop below would overwrite a variable on every turn, and only the
        # last joint would survive.
        self.home_dir = []
        self.home_offset_rad = []
        self.max_abs_rad = []

        for name in JOINT_NAMES:
            self.declare_parameter(f"hardware.joints.{name}.home_dir", -1) # which way to look FIRST, +1 or -1
            home_dir = int(self.get_parameter(f"hardware.joints.{name}.home_dir").value)

            self.declare_parameter(f"hardware.joints.{name}.home_offset_rad", 0.1) # how far zero sits off the switch
            home_offset_rad = float(self.get_parameter(f"hardware.joints.{name}.home_offset_rad").value)

            self.declare_parameter(f"hardware.joints.{name}.max_abs_rad", 1.0) # the guard the bridge refuses targets beyond
            max_abs_rad = float(self.get_parameter(f"hardware.joints.{name}.max_abs_rad").value)

            self.home_dir.append(1 if home_dir >= 0 else -1) # anything but a clean +1 / -1 is forced into one
            self.home_offset_rad.append(abs(home_offset_rad)) # a distance, never a direction: home_dir decides that
            self.max_abs_rad.append(max_abs_rad)

            self.get_logger().debug(f"{name}: look towards {self.home_dir[-1]:+d} first, zero {self.home_offset_rad[-1]} rad off the switch, guard +/-{max_abs_rad} rad")


        for name, rad, limit in zip(JOINT_NAMES, self.start_pose_rad, self.max_abs_rad):
            if abs(rad) > limit:
                self.get_logger().warn(f"homing.start_pose_rad asks {rad} rad for {name}, outside its +/-{limit} rad guard. It will be trimmed to the guard.")


        # Names into indices. A name that does not exist is refused out loud:
        # a typo would otherwise quietly home one joint less than asked.
        self.queue = []
        for name in wanted:
            if name not in JOINT_NAMES:
                self.get_logger().error(f"Unknown joint '{name}' in homing.joints. The joints are: {', '.join(JOINT_NAMES)}")
                continue
            self.queue.append(JOINT_NAMES.index(name))


        self.position = None    # None until the first /robot/joint_states arrives
        self.switches = None    # None until the first /robot/sensor_states arrives

        self.index = 0          # the joint being homed right now
        self.state = "next"     # what we are doing with that joint
        self.start_rad = 0.0    # where this joint started: the point to come back to
        self.dir = -1           # the way we are looking right now, +1 or -1
        self.tries = 0          # 1 while looking the first way, 2 the second
        self.to_place = []      # joints still to move to the start pose
        self.goal_rad = 0.0     # the home position, once the switch has been found
        self.homed = [0] * len(JOINT_NAMES) # 1 for a joint whose zero this node found


        self.target_publisher = self.create_publisher(Float64MultiArray, '/robot/target_rad', 10)
        self.command_publisher = self.create_publisher(String, '/robot/command', 10)

        # transient_local keeps the last value and hands it to whoever
        # subscribes **later**. Without it, a node started after homing would
        # never find out which joints are calibrated: the message is long gone.
        self.homed_publisher = self.create_publisher(UInt8MultiArray, '/robot/homed', QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.publish_homed()

        self.joint_state_subscriber = self.create_subscription(JointState, '/robot/joint_states', self.on_joint_states, 10)
        self.sensor_states_subscriber = self.create_subscription(UInt8MultiArray, '/robot/sensor_states', self.on_sensor_states, 10)

        # The timer is what makes this node act: **nothing happens on its own**.
        self.timer = self.create_timer(1.0 / rate_hz, self.on_timer)


        if not self.queue:
            self.state = "done"
            self.get_logger().error("homing.joints holds no joint this node knows: there is nothing to home. Nothing will be sent to the arm.")
        else:
            self.get_logger().info(f"Homing ready. Joints to home, in order: {', '.join(JOINT_NAMES[i] for i in self.queue)}. Waiting for the bridge.")



    # Arduino -> here, through the bridge

    def on_joint_states(self, msg):
        """Where the arm really is, in radians."""
        if len(msg.position) != len(JOINT_NAMES):
            self.get_logger().error(f"Expected {len(JOINT_NAMES)} positions, got {len(msg.position)}")
            return
        self.position = list(msg.position)


    def on_sensor_states(self, msg):
        """The six limit switches, 1 pressed and 0 free, in joint order."""
        if len(msg.data) != len(JOINT_NAMES):
            self.get_logger().error(f"Expected {len(JOINT_NAMES)} switches, got {len(msg.data)}")
            return
        self.switches = list(msg.data)



    # The search

    def on_timer(self):
        """One small decision per tick. Nothing in here waits for anything."""
        if self.state == "done":
            return

        # We refuse to move an arm whose position and switches we do not know.
        if self.position is None or self.switches is None:
            self.get_logger().info("Waiting for /robot/joint_states and /robot/sensor_states. Is the bridge running?", once=True)
            return

        if self.state == "next":
            self.next_joint()
            return

        if self.state == "start":
            self.goto_start()
            return

        name = JOINT_NAMES[self.index]

        # Why this joint may go no further the way it is going, if so. Worked
        # out here because it means the same thing in both searching states.
        blocked = self.no_further()

        if self.state == "clear":
            # Already standing on the switch, so there is no closing edge left
            # to find. Step off it, then search as usual.
            if not self.switches[self.index]:
                self.state = "search"
            elif blocked:
                self.turn_around(f"{name}: the switch never released towards {-self.dir:+d}, {blocked}")
            else:
                self.creep(-self.dir)

        elif self.state == "search":
            if self.switches[self.index]:
                self.found()
            elif blocked:
                self.turn_around(f"{name}: no switch towards {self.dir:+d}, {blocked}")
            else:
                self.creep(self.dir)

        elif self.state == "return":
            # Straight back to where this joint started, so the other way gets
            # the whole of search_rad to itself. One absolute target: we are
            # retracing ground we have just covered, there is nothing new to
            # run into, so there is nothing to creep for.
            self.send_target(self.start_rad)
            if abs(self.position[self.index] - self.start_rad) <= self.tolerance_rad:
                self.begin_try()

        elif self.state == "offset":
            # Moving AWAY from the switch, so there is nothing to watch for:
            # one absolute target is enough, asked again until we get there.
            self.send_target(self.goal_rad)
            if abs(self.position[self.index] - self.goal_rad) <= self.tolerance_rad:
                self.done_joint()


    def next_joint(self):
        """Take the next joint off the queue, or finish if there is none left."""
        if not self.queue:
            self.finish()
            return

        self.index = self.queue.pop(0)
        self.start_rad = self.position[self.index] # never changed again: this is home base
        self.dir = self.home_dir[self.index]       # the way to look first
        self.tries = 0

        self.get_logger().info(f"{JOINT_NAMES[self.index]}: homing from {self.start_rad:.3f} rad, up to {self.search_rad} rad each way.")
        self.begin_try()


    def begin_try(self):
        """Start looking, whichever way self.dir happens to point now."""
        name = JOINT_NAMES[self.index]
        self.tries = self.tries + 1

        if self.switches[self.index]:
            self.state = "clear"
            self.get_logger().warn(f"{name}: switch is ALREADY pressed, stepping off it towards {-self.dir:+d} first.")
        else:
            self.state = "search"
            self.get_logger().info(f"{name}: looking for the switch towards {self.dir:+d}.")


    def turn_around(self, why):
        """That way gave nothing: back to the start and look the other way.

        Which is why home_dir is only a HINT about where the switch is. It
        saves this whole second trip when it is right, and costs nothing but
        time when it is wrong.
        """
        if self.tries >= 2:
            self.give_up(f"{why}, and nothing the other way either. Is that limit switch wired and working? Watch it with: ros2 topic echo /robot/sensor_states")
            return

        self.dir = -self.dir
        self.state = "return"
        self.get_logger().warn(f"{why}. Going back to {self.start_rad:.3f} rad to look the other way.")


    def found(self):
        """The switch closed: this is the angle the whole joint is measured from."""
        name = JOINT_NAMES[self.index]
        touch = self.position[self.index]
        self.goal_rad = touch - self.dir * self.home_offset_rad[self.index]
        self.state = "offset"
        self.get_logger().info(f"{name}: switch found at {touch:.3f} rad, home position is {self.goal_rad:.3f} rad.")


    def done_joint(self):
        """This joint stands on its home position: on to the next one."""
        name = JOINT_NAMES[self.index]
        if self.switches[self.index]:
            self.get_logger().warn(f"{name}: the switch is STILL pressed on the home position. Raise hardware.joints.{name}.home_offset_rad, or the firmware will keep refusing one direction of this joint.")
        # Marked, but not announced yet: this joint is standing on the right
        # spot, and its angle only becomes 0 when finish() sends the "zero".
        self.homed[self.index] = 1
        self.get_logger().info(f"{name}: homed, standing at {self.position[self.index]:.3f} rad.")
        self.state = "next"


    def no_further(self):
        """Why this joint may go no further, or None while it still may.

        Two limits, whichever comes first:

          - search_rad from where the joint started, in BOTH directions;
          - the max_abs_rad guard.

        The second one is not optional. The bridge REFUSES a target past
        max_abs_rad instead of trimming it, so without this check the joint
        would simply stop, and search_rad would never be reached because the
        position never changes again: the search would wait for ever. That is
        exactly what happened with search_rad 2.0 on an elbow guarded at 1.84.
        """
        here = self.position[self.index]

        if abs(here - self.start_rad) >= self.search_rad:
            return f"searched the whole {self.search_rad} rad"

        if abs(here) >= self.guard_rad() - self.tolerance_rad:
            return f"reached the +/-{self.max_abs_rad[self.index]} rad guard (hardware.joints.{JOINT_NAMES[self.index]}.max_abs_rad)"

        return None


    def guard_rad(self):
        """The widest angle the bridge will accept for the joint being homed."""
        return self.max_abs_rad[self.index] - self.tolerance_rad


    def give_up(self, why):
        """Stop the arm, say what went wrong, and zero nothing."""
        self.send_command("halt")
        self.state = "done"
        # No "zero" was ever sent, so not one joint is calibrated, not even the
        # ones that did find their switch before this one failed.
        self.homed = [0] * len(JOINT_NAMES)
        self.publish_homed()
        self.get_logger().error(why)
        self.get_logger().error("Homing stopped. Nothing was zeroed, so 0 rad still means nothing.")


    def finish(self):
        """Every joint stands on its home position: call this whole pose zero."""
        self.send_command("zero")
        self.publish_homed()
        done = ", ".join(name for name, ok in zip(JOINT_NAMES, self.homed) if ok)
        self.get_logger().info(f"All joints homed. Sent 'zero': this pose is 0 rad on every joint from now on. Calibrated: {done}.")

        # Forget where we think the arm is. "zero" has just moved the whole
        # coordinate frame out from under us, and self.position still holds the
        # old numbers until the next position_steps line arrives, a tenth of a
        # second from now. A target built from those would ask every joint for
        # its OLD angle measured from the NEW zero, and the arm would lurch by
        # its own home offsets the instant it finished homing. The guard at the
        # top of on_timer does the waiting for us.
        self.position = None

        moving = ", ".join(f"{name} to {rad:.3f}" for name, rad in zip(JOINT_NAMES, self.start_pose_rad) if abs(rad) > self.tolerance_rad)
        if moving:
            self.get_logger().info(f"Now the start pose, one joint at a time: {moving}.")

        self.to_place = list(range(len(JOINT_NAMES)))
        self.state = "start"


    def goto_start(self):
        """Walk the arm to its start pose, ONE JOINT AT A TIME.

        One at a time, and not all six together, because nothing anywhere in
        this stack knows what the arm might swing into: there is no collision
        checking and no model of the desk. Six joints moving at once is a hope.

        A home position sits home_offset_rad off a limit switch, so parking
        there leaves every joint right next to its own end of travel. The start
        pose is where the arm is actually meant to wait.
        """
        if not self.to_place:
            self.state = "done"
            self.get_logger().info(f"At the start pose {[round(rad, 3) for rad in self.start_pose_rad]}. Ready.")
            return

        self.index = self.to_place[0]
        goal = self.start_pose_rad[self.index]

        if abs(self.position[self.index] - goal) <= self.tolerance_rad:
            self.to_place.pop(0)
            return

        self.send_target(goal)



    # Sending

    def creep(self, direction):
        """Ask for a target one small step past where the joint REALLY is.

        Measuring the step from the real position instead of from the last
        target is what keeps the arm slow: the target can never get more than
        one step ahead of the arm, so the arm sets the pace, not this node.
        """
        self.send_target(self.position[self.index] + direction * self.step_rad)


    def send_target(self, rad):
        """One message with all six angles, because the bridge wants them all.

        The five joints we are not homing are asked to stay exactly where they
        already are.
        """
        target = list(self.position)
        # Kept inside the guard, so the bridge never has to refuse the message.
        # no_further() has already stopped the search by the time we get here.
        target[self.index] = max(-self.guard_rad(), min(self.guard_rad(), rad))

        msg = Float64MultiArray()
        msg.data = [float(v) for v in target]
        self.target_publisher.publish(msg)


    def publish_homed(self):
        """Which joints have a zero that means something, 1 yes and 0 no.

        Reset to all zeros by every Arduino reset, which includes opening the
        serial port: nobody may believe this until homing has run again.
        """
        msg = UInt8MultiArray()
        msg.data = self.homed
        self.homed_publisher.publish(msg)


    def send_command(self, word):
        """One word straight through the bridge to the firmware."""
        msg = String()
        msg.data = word
        self.command_publisher.publish(msg)



def main():
    node = None
    rclpy.init()
    try:
        node = Homing("homing_node")
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()




if __name__ == "__main__":
    main()
