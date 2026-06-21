"""Mark 1 Stage 1 sim bring-up — headless Gazebo Harmonic + the rover + control.

  ros2 launch friday_description sim.launch.py

Brings up: gz sim (server, headless) with the ground world; robot_state_publisher
from the rocker-bogie xacro; spawns the rover; bridges /clock; then loads the
joint_state_broadcaster + diff_drive_controller. Drive it with a Twist on
/diff_drive_controller/cmd_vel (remapped to /mark1/locomotion/cmd_vel).
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


def generate_launch_description() -> LaunchDescription:
    pkg = get_package_share_directory('friday_description')
    ros_gz_sim = get_package_share_directory('ros_gz_sim')

    xacro_file = os.path.join(pkg, 'urdf', 'mark1.urdf.xacro')
    controllers_yaml = os.path.join(pkg, 'config', 'diff_drive_controller.yaml')
    world_path = PathJoinSubstitution([pkg, 'worlds', LaunchConfiguration('world')])

    robot_description = ParameterValue(
        Command(['xacro ', xacro_file, ' controllers_yaml:=', controllers_yaml],
                on_stderr='ignore'),
        value_type=str)

    # Gazebo Harmonic. headless:=true -> server only (-s); false -> open the GUI.
    gz_src = PythonLaunchDescriptionSource(
        os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py'))
    headless = LaunchConfiguration('headless')
    gz_headless = IncludeLaunchDescription(
        gz_src, condition=IfCondition(headless),
        launch_arguments={'gz_args': [TextSubstitution(text='-r -s -v1 '),
                                      world_path]}.items())
    gz_gui = IncludeLaunchDescription(
        gz_src, condition=UnlessCondition(headless),
        launch_arguments={'gz_args': [TextSubstitution(text='-r -v1 '),
                                      world_path]}.items())

    rsp = Node(
        package='robot_state_publisher', executable='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_description, 'use_sim_time': True}],
    )

    # /clock from gz so everything runs on sim time.
    bridge = Node(
        package='ros_gz_bridge', executable='parameter_bridge', output='screen',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
    )

    spawn = Node(
        package='ros_gz_sim', executable='create', output='screen',
        arguments=['-topic', 'robot_description', '-name', 'mark1', '-z', '0.15'],
    )

    jsb = Node(
        package='controller_manager', executable='spawner', output='screen',
        arguments=['joint_state_broadcaster'],
    )
    ddc = Node(
        package='controller_manager', executable='spawner', output='screen',
        arguments=['diff_drive_controller',
                   '--param-file', controllers_yaml],
        remappings=[('/diff_drive_controller/cmd_vel', '/mark1/locomotion/cmd_vel')],
    )

    # Load controllers once the model (and its gz_ros2_control manager) is up.
    load_after_spawn = RegisterEventHandler(
        OnProcessExit(target_action=spawn, on_exit=[TimerAction(period=2.0, actions=[jsb])]))
    load_ddc_after_jsb = RegisterEventHandler(
        OnProcessExit(target_action=jsb, on_exit=[ddc]))

    return LaunchDescription([
        DeclareLaunchArgument('world', default_value='empty_ground.sdf',
                              description='world file in friday_description/worlds'),
        DeclareLaunchArgument('headless', default_value='true',
                              description='true = server only; false = open the Gazebo GUI'),
        gz_headless, gz_gui, rsp, bridge, spawn, load_after_spawn, load_ddc_after_jsb,
    ])
