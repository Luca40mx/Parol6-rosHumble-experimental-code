import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
import time


class TestNodePython(Node):

    def __init__(self, node_name: str):

        super().__init__(node_name)

        self.counter = 0

        self.declare_parameter("common.log_level", 20) 
        self.declare_parameter("common.robot_name", "nome a caso sbagliato!")

        log_level = self.get_parameter("common.log_level").value
        self.get_logger().set_level(log_level)

        robot_name = self.get_parameter("common.robot_name")
        self.get_logger().info(robot_name.value)

        self.get_logger().info("Node started!")

    def timer(self):
        self.counter = self.counter + 1
        time.sleep(0.2)
        self.get_logger().info(f"Ciao dalla funzione timer: {self.counter}")

    def compute_frequency(self):
        frequency = 1 / (self.counter + 1)
        self.get_logger().info(f"Ciao questa è la frequenza dalla funzione compute_frequency: {frequency}")


        





def main():

    rclpy.init()

    node = TestNodePython("nome_che_vuoi_dare_al_nodo")
    node.compute_frequency()

    while True:
        node.timer()
    

    
    rclpy.spin(node)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
