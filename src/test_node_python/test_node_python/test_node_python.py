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
