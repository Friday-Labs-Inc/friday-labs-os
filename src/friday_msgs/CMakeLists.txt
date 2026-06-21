cmake_minimum_required(VERSION 3.8)
project(friday_msgs)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Mark1Header.msg"
  "msg/Heartbeat.msg"
  "msg/HealthStatus.msg"
  "msg/ModulePresence.msg"
  "msg/MotionCommand.msg"
  "msg/FaultReport.msg"
  "msg/AuthorityLease.msg"
  "msg/EmergencyStop.msg"
  "srv/RegisterModule.srv"
  DEPENDENCIES builtin_interfaces
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
