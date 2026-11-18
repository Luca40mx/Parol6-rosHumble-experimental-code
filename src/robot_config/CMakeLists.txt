cmake_minimum_required(VERSION 3.8)
project(robot_config)

find_package(ament_cmake REQUIRED)

# Questo pacchetto non contiene codice: installa solo config/, cioe' i file
# YAML che vengono passati come parametri ai nodi. Ogni file che aggiungi in
# quella cartella viene installato da solo.
# Chi avvia i nodi e' robot_bringup, che legge gli YAML da qui.
install(DIRECTORY config
  DESTINATION share/${PROJECT_NAME})

ament_package()
