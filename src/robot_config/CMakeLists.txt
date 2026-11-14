cmake_minimum_required(VERSION 3.8)
project(robot_config)

find_package(ament_cmake REQUIRED)

# This package contains no code to compile. It only installs the config/ and
# launch/ folders, so that ROS can find them after `colcon build`.
# Every file you add to these folders is installed automatically.
install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME})

ament_package()
