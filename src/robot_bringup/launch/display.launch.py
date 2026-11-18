"""Mostra il modello del braccio in RViz, con i cursori per muoverlo.

    ros2 launch robot_bringup display.launch.py

Non serve l'Arduino: i cursori pubblicano loro gli angoli su /joint_states.
Serve per controllare l'URDF e le mesh, non per guardare il robot vero.

I tre nodi che partono:
  robot_state_publisher   dagli angoli calcola dove sta ogni pezzo -> /tf
  joint_state_publisher_gui   la finestrella coi sei cursori
  rviz2                   disegna /tf
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # Tre pacchetti in gioco, quindi tre percorsi: il modello sta in
    # robot_description, la disposizione di RViz sta qui in robot_bringup, e
    # i parametri YAML (che questo launch non usa) stanno in robot_config.
    description_pkg = get_package_share_directory('robot_description')
    bringup_pkg = get_package_share_directory('robot_bringup')

    urdf_file = os.path.join(description_pkg, 'urdf', 'parol6.urdf')
    rviz_file = os.path.join(bringup_pkg, 'rviz', 'parol6.rviz')

    with open(urdf_file, 'r') as f:
        robot_description = f.read()

    return LaunchDescription([
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{'robot_description': robot_description}],
            output='screen',
        ),
        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            output='screen',
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', rviz_file],
            output='screen',
        ),
    ])
