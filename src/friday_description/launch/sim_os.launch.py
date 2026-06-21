"""Mark 1 Stage 1 — the REAL rover OS driving the Gazebo physics rover.

Brings up the physics layer (Gazebo + the rocker-bogie + diff_drive_controller)
AND the actual OS:
  * Core Hub  — publishes the authority lease + 20 Hz safety pulse, and supervises
    the Locomotion lifecycle (configure -> activate).
  * Locomotion agent — Phase 4 authority enforcement + safe-stop watchdog; its
    accepted, safe-stop-gated (v, w) is emitted as a wheel command to
    diff_drive_controller (param wheel_cmd_topic), so it drives Gazebo physics.

Result: an authorized MotionCommand drives the *physical* (simulated) rover, and
losing the safety pulse (e.g. the Core dies) safe-stops it — Phase 4 against physics.

  ros2 launch friday_description sim_os.launch.py
  # then publish a MotionCommand as the authority holder MARK1-CORE-001 on
  # /mark1/locomotion/cmd_motion
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    IncludeLaunchDescription,
    RegisterEventHandler,
    TimerAction,
)
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

WHEEL_CMD_TOPIC = '/diff_drive_controller/cmd_vel'


def generate_launch_description() -> LaunchDescription:
    pkg = get_package_share_directory('friday_description')
    ros_gz_sim = get_package_share_directory('ros_gz_sim')
    xacro_file = os.path.join(pkg, 'urdf', 'mark1.urdf.xacro')
    controllers_yaml = os.path.join(pkg, 'config', 'diff_drive_controller.yaml')
    world_file = os.path.join(pkg, 'worlds', 'empty_ground.sdf')

    robot_description = ParameterValue(
        Command(['xacro ', xacro_file, ' controllers_yaml:=', controllers_yaml],
                on_stderr='ignore'),
        value_type=str)

    # ---- physics layer ----
    gz = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': f'-r -s -v1 {world_file}'}.items())
    rsp = Node(
        package='robot_state_publisher', executable='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_description, 'use_sim_time': True}])
    bridge = Node(
        package='ros_gz_bridge', executable='parameter_bridge', output='screen',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'])
    spawn = Node(
        package='ros_gz_sim', executable='create', output='screen',
        arguments=['-topic', 'robot_description', '-name', 'mark1', '-z', '0.15'])
    jsb = Node(
        package='controller_manager', executable='spawner', output='screen',
        arguments=['joint_state_broadcaster'])
    ddc = Node(
        package='controller_manager', executable='spawner', output='screen',
        arguments=['diff_drive_controller', '--param-file', controllers_yaml])
    load_jsb = RegisterEventHandler(
        OnProcessExit(target_action=spawn, on_exit=[TimerAction(period=2.0, actions=[jsb])]))
    load_ddc = RegisterEventHandler(
        OnProcessExit(target_action=jsb, on_exit=[ddc]))

    # ---- the real OS ----
    core = Node(
        package='friday_core_hub', executable='core_hub', name='core_hub',
        output='screen',
        parameters=[{'managed_nodes': ['locomotion'], 'autostart_delay_s': 8.0}])
    loco = Node(
        package='friday_locomotion', executable='locomotion_agent', name='locomotion',
        output='screen',
        parameters=[{'wheel_cmd_topic': WHEEL_CMD_TOPIC}])

    return LaunchDescription([
        gz, rsp, bridge, spawn, load_jsb, load_ddc, core, loco,
    ])
