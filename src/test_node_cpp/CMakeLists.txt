cmake_minimum_required(VERSION 3.8)
project(test_node_cpp)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)

# Build an executable from our source file. The first argument is the
# EXECUTABLE name, which is what you type after 'ros2 run test_node_cpp'.
add_executable(test_node_cpp src/test_node_cpp.cpp)

# Give the executable the include paths and libraries of rclcpp.
ament_target_dependencies(test_node_cpp rclcpp)

# Install the executable into lib/<package>, where 'ros2 run' looks for it.
install(TARGETS test_node_cpp
  DESTINATION lib/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
