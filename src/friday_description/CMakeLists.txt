cmake_minimum_required(VERSION 3.8)
project(friday_description)

find_package(ament_cmake REQUIRED)

# Install the sim assets to the package share dir (launch finds them there).
install(
  DIRECTORY urdf worlds config launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
