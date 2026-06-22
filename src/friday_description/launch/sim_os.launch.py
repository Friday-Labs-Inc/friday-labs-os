"""Mark 1 Stage 1 — the REAL rover OS driving the corner-steer Gazebo rover.

  ros2 launch friday_description sim_os.launch.py [world:=bumpy.sdf] [headless:=false]

Brings up the physics layer (Gazebo + the rocker-bogie + wheel-velocity & corner-
steer controllers) AND the real OS:
  * Core Hub  — publishes the authority lease + 20 Hz safety pulse, supervises the
    Locomotion lifecycle.
  * Locomotion agent — Phase 4 authority enforcement + safe-stop watchdog; converts
    an authorized MotionCommand (v, w) into 6 wheel velocities + 4 Ackermann corner
    steer angles (kinematics.drive_and_steer) and commands the gz controllers.

Result: an authorized MotionCommand drives the physics rover via the real OS, and
losing the safety pulse (Core dies) safe-stops it. Send commands as the holder
MARK1-CORE-001 on /mark1/locomotion/cmd_motion.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    RegisterEventHandler,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    LaunchConfiguration,
    PathJoinSubstitution,
    TextSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

WHEEL_CMD = '/wheel_velocity_controller/commands'
STEER_CMD = '/steer_position_controller/commands'


def generate_launch_description() -> LaunchDescription:
    pkg = get_package_share_directory('friday_description')
    ros_gz_sim = get_package_share_directory('ros_gz_sim')
    xacro_file = os.path.join(pkg, 'urdf', 'mark1.urdf.xacro')
    controllers_yaml = os.path.join(pkg, 'config', 'controllers.yaml')
    world_path = PathJoinSubstitution([pkg, 'worlds', LaunchConfiguration('world')])

    robot_description = ParameterValue(
        Command(['xacro ', xacro_file, ' controllers_yaml:=', controllers_yaml],
                on_stderr='ignore'),
        value_type=str)

    # ---- physics + control layer ----
    gz_src = PythonLaunchDescriptionSource(
        os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py'))
    headless = LaunchConfiguration('headless')
    gz_headless = IncludeLaunchDescription(
        gz_src, condition=IfCondition(headless),
        launch_arguments={'gz_args': [TextSubstitution(text='-r -s -v1 '), world_path]}.items())
    gz_gui = IncludeLaunchDescription(
        gz_src, condition=UnlessCondition(headless),
        launch_arguments={'gz_args': [TextSubstitution(text='-r -v1 '), world_path]}.items())

    rsp = Node(package='robot_state_publisher', executable='robot_state_publisher',
               output='screen',
               parameters=[{'robot_description': robot_description, 'use_sim_time': True}])
    bridge = Node(package='ros_gz_bridge', executable='parameter_bridge', output='screen',
                  arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'])
    spawn = Node(package='ros_gz_sim', executable='create', output='screen',
                 arguments=['-topic', 'robot_description', '-name', 'mark1', '-z', '0.12'])

    def spawner(name):
        return Node(package='controller_manager', executable='spawner', output='screen',
                    arguments=[name, '--param-file', controllers_yaml])

    jsb = spawner('joint_state_broadcaster')
    wheels = spawner('wheel_velocity_controller')
    steer = spawner('steer_position_controller')
    load_jsb = RegisterEventHandler(
        OnProcessExit(target_action=spawn, on_exit=[TimerAction(period=2.0, actions=[jsb])]))
    load_ctrls = RegisterEventHandler(
        OnProcessExit(target_action=jsb, on_exit=[wheels, steer]))

    # ---- the real OS ----
    core = Node(package='friday_core_hub', executable='core_hub', name='core_hub',
                output='screen',
                parameters=[{'managed_nodes': ['locomotion'], 'autostart_delay_s': 10.0}])
    loco = Node(package='friday_locomotion', executable='locomotion_agent', name='locomotion',
                output='screen',
                parameters=[{'wheel_cmd_topic': WHEEL_CMD, 'steer_cmd_topic': STEER_CMD,
                             'safe_stop_timeout_s': 0.6}])

    return LaunchDescription([
        DeclareLaunchArgument('world', default_value='empty_ground.sdf'),
        DeclareLaunchArgument('headless', default_value='true'),
        gz_headless, gz_gui, rsp, bridge, spawn, load_jsb, load_ctrls, core, loco,
    ])
