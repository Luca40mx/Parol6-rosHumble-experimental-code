"""Start the robot nodes and give each of them ALL the YAML files in config/."""

import glob
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import SetEnvironmentVariable
from launch_ros.actions import Node


def generate_launch_description():
    # Folder where the config/ directory of this package was installed.
    config_dir = os.path.join(
        get_package_share_directory('robot_config'), 'config')

    # Collect EVERY .yaml file found in config/. Adding a new YAML file there
    # (and running `colcon build`) is enough: this file does not change.
    # Files are loaded in alphabetical order. If two files define the same
    # parameter, the file loaded LAST wins.
    param_files = sorted(glob.glob(os.path.join(config_dir, '*.yaml')))

    return LaunchDescription([
        # Colour the log by severity: green DEBUG, yellow WARN, red ERROR.
        # The colours are built into ROS, but rcutils only emits them when it
        # believes a human is watching, and `ros2 launch` captures each node's
        # output through a pipe to prefix it with [bridge-1]. Seeing a pipe,
        # rcutils gives up on colour, so it has to be told explicitly.
        SetEnvironmentVariable('RCUTILS_COLORIZED_OUTPUT', '1'),
        # Drop {time} from the line. The default format puts seconds since 1970
        # in every message, which is exact and unreadable. The order of the
        # lines already tells the order of events.
        # Other placeholders available: {function_name} {file_name} {line_number}
        SetEnvironmentVariable('RCUTILS_CONSOLE_OUTPUT_FORMAT',
                               '[{severity}] [{name}]: {message}'),

        # One Node(...) block per node to start. To start a new node, copy a
        # block, change `package` and `executable`, and keep `parameters`.
        # Node(
        #     package='test_node_python',      # where the program is
        #     executable='test_node_python',   # name of the code to run
        #     parameters=param_files,          # the yaml files to load with the parameters
        #     output='screen',                 # print log messages to the terminal
        # ),
        Node(
            package='arduino_ros_bridge',
            executable='bridge',
            parameters=param_files,
            output='screen',
        ),
    ])
