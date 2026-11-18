"""Start the homing node, with ALL the YAML files in config/.

Homing is not part of robot_bridge.launch.py on purpose: it MOVES THE ARM as
soon as it starts. Start it by hand, when you mean it.

The bridge has to be running already, in another terminal:
    ros2 launch robot_bringup robot_bridge.launch.py
"""

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

    # Every .yaml file in config/, exactly like in robot_bridge.launch.py.
    param_files = sorted(glob.glob(os.path.join(config_dir, '*.yaml')))

    return LaunchDescription([
        # Same colours and same line format as the other launch file.
        SetEnvironmentVariable('RCUTILS_COLORIZED_OUTPUT', '1'),
        SetEnvironmentVariable('RCUTILS_CONSOLE_OUTPUT_FORMAT',
                               '[{severity}] [{name}]: {message}'),

        Node(
            package='robot_homing',
            executable='homing',
            parameters=param_files,
            output='screen',
        ),
    ])
