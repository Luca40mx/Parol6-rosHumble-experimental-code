// Minimal ROS 2 C++ node that logs a message once per second.

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"

// Enables time literals such as 1s (one second).
using namespace std::chrono_literals;

// A node is a class that inherits from rclcpp::Node.
class TestNodeCpp : public rclcpp::Node
{
public:
  TestNodeCpp()
  // Call the Node constructor and give this node its ROS name.
  // This is the NODE name shown by 'ros2 node list'. It is independent
  // of the EXECUTABLE name, which is defined in CMakeLists.txt.
  : Node("test_node_cpp"), count_(0)
  {
    // Create a timer that calls on_timer() every second. A "wall" timer
    // follows the real clock. The lambda captures 'this' so the callback
    // can reach the members of this object.
    timer_ = this->create_wall_timer(1s, [this]() {this->on_timer();});

    // STEP 1 - declare every parameter this node wants to use, with a
    // default value. The default is used when no YAML file provides the
    // parameter (for example with a plain 'ros2 run'). The type given between
    // < > is the TYPE of the parameter. The name is "<prefix>.<key>" as
    // written in the YAML files of the robot_config package.
    this->declare_parameter<int>("common.log_level", 20);
    this->declare_parameter<std::string>("common.robot_name", "not_set");
    this->declare_parameter<std::string>("hardware.port", "not_set");
    this->declare_parameter<int>("hardware.num_joints", 0);
    this->declare_parameter<double>("software.control_rate_hz", 0.0);

    // STEP 2 - read the current value with the accessor that matches the
    // type: as_string(), as_int(), as_double(), as_bool().
    // Apply the logging level chosen in common.yaml to THIS node. From now
    // on, messages less serious than this level are not printed.
    this->get_logger().set_level(static_cast<rclcpp::Logger::Level>(this->get_parameter("common.log_level").as_int()));

    const std::string robot_name = this->get_parameter("common.robot_name").as_string();
    const std::string port = this->get_parameter("hardware.port").as_string();
    const int64_t num_joints = this->get_parameter("hardware.num_joints").as_int();
    const double rate_hz = this->get_parameter("software.control_rate_hz").as_double();

    RCLCPP_INFO(
      this->get_logger(),
      "Config: robot_name=%s, port=%s, num_joints=%ld, control_rate_hz=%.1f",
      robot_name.c_str(), port.c_str(), static_cast<long>(num_joints), rate_hz);

    RCLCPP_INFO(this->get_logger(), "Node started. Press Ctrl+C to stop.");
  }

private:
  // Runs once per timer period.
  void on_timer()
  {
    ++count_;
    // RCLCPP_INFO is a logging macro with printf-style formatting. Messages
    // are printed in the terminal, tagged with the node name and a timestamp.
    RCLCPP_INFO(this->get_logger(), "Hello from C++, tick %zu", count_);
  }

  // The timer must be stored as a member. If this shared pointer were
  // destroyed, the timer would be cancelled.
  rclcpp::TimerBase::SharedPtr timer_;

  // Counter used only to make each log line different.
  std::size_t count_;
};

int main(int argc, char * argv[])
{
  // Initialize the ROS 2 client library. This also installs a signal
  // handler, so Ctrl+C requests a clean shutdown instead of killing us.
  rclcpp::init(argc, argv);

  // Create the node inside a shared pointer, then spin it. spin() blocks
  // here and runs callbacks (our timer) until shutdown is requested.
  rclcpp::spin(std::make_shared<TestNodeCpp>());

  // Release ROS resources. Safe to call even after Ctrl+C.
  rclcpp::shutdown();
  return 0;
}
