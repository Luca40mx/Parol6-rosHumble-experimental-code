cmake_minimum_required(VERSION 3.8)
project(robot_bringup)

find_package(ament_cmake REQUIRED)

# Nessun codice da compilare: installa i launch file e la disposizione di
# RViz. I parametri YAML stanno in robot_config, e i launch li leggono da la'.
install(DIRECTORY launch rviz
  DESTINATION share/${PROJECT_NAME})

ament_package()
