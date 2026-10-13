// Minimal ROS 2 C++ node that logs a message once per second.

#include <chrono>
#include <cstddef>
#include <memory>

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
