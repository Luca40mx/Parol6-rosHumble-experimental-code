"""Minimal ROS 2 Python node that logs a message once per second."""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node


class TestNodePython(Node):
    """A node that owns one timer and logs a message on every tick."""

    def __init__(self):
        # Call the Node constructor and give this node its ROS name.
        # This is the NODE name shown by 'ros2 node list'. It is independent
        # of the EXECUTABLE name, which is defined in setup.py.
        super().__init__('test_node_python')

        # Counter used only to make each log line different.
        self._count = 0

        # Create a timer that calls self._on_timer every 1.0 second.
        # The timer only fires while the node is being "spun" (see main).
        self._timer = self.create_timer(1.0, self._on_timer)

        # STEP 1 - declare every parameter this node wants to use, with a
        # default value. The default is used when no YAML file provides the
        # parameter (for example with a plain 'ros2 run'). The default also
        # fixes the TYPE of the parameter: 0 is an integer, 0.0 a float, 'x' a
        # string, False a boolean. The name is "<prefix>.<key>" as written in
        # the YAML files of the robot_config package.
        self.declare_parameter('common.log_level', 20) # 20 is the default value if the value is missing in the YAML file; 10=debug, 20=info, 30=warn, 40=error, 50=fatal
        self.declare_parameter('common.robot_name', 'not_set')
        self.declare_parameter('hardware.port', 'not_set')
        self.declare_parameter('hardware.num_joints', 0)
        self.declare_parameter('software.control_rate_hz', 0.0)

        # STEP 2 - read the current value. '.value' returns a normal Python
        # str / int / float / bool.
        # Apply the logging level chosen in common.yaml to THIS node. From now
        # on, messages less serious than this level are not printed.
        log_level = self.get_parameter('common.log_level')
        self.get_logger().set_level(log_level.value)

        robot_name = self.get_parameter('common.robot_name').value
        port = self.get_parameter('hardware.port').value
        num_joints = self.get_parameter('hardware.num_joints').value
        rate_hz = self.get_parameter('software.control_rate_hz').value

        self.get_logger().info(
            f'Config: robot_name={robot_name}, port={port}, '
            f'num_joints={num_joints}, control_rate_hz={rate_hz}')

        self.get_logger().info('Node started. Press Ctrl+C to stop.')

    def _on_timer(self):
        """Run once per timer period."""
        self._count += 1
        # get_logger() returns this node's logger. Messages are printed in
        # the terminal and tagged with the node name and a timestamp.
        self.get_logger().info(f'Hello from Python, tick {self._count}')


def main(args=None):
    """Entry point registered in setup.py under console_scripts."""
    # Initialize the ROS 2 client library. This must happen before any
    # node is created.
    rclpy.init(args=args)

    node = TestNodePython()

    try:
        # spin() blocks here and runs callbacks (our timer) until shutdown.
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        # Ctrl+C raises KeyboardInterrupt. A shutdown requested from outside
        # raises ExternalShutdownException. Both are normal ways to stop.
        pass
    finally:
        # Release the node's resources, then shut ROS down. try_shutdown()
        # is safe even when Ctrl+C has already shut the context down.
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
