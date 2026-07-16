"""Mark 1 Stage 1 sim bring-up — headless/GUI Gazebo Harmonic + the rover + control.

  ros2 launch friday_description sim.launch.py [world:=bumpy.sdf] [headless:=false]

Brings up gz sim with a world, robot_state_publisher from the rocker-bogie xacro,
spawns the rover, bridges /clock, then loads joint_state_broadcaster +
wheel_velocity_controller (6 drive wheels) + steer_position_controller (4 corner
steer). Drive with Float64MultiArray on /wheel_velocity_controller/commands (rad/s)
and steer with /steer_position_controller/commands (rad).
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
    controllers_yaml = os.path.join(pkg, 'config', 'controllers.yaml')
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
        parameters=[{'robot_description': robot_description, 'use_sim_time': True}])

    bridge = Node(
        package='ros_gz_bridge', executable='parameter_bridge', output='screen',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
                             '/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
                             '/imu@sensor_msgs/msg/Imu[gz.msgs.IMU'])

    spawn = Node(
        package='ros_gz_sim', executable='create', output='screen',
        arguments=['-topic', 'robot_description', '-name', 'mark1', '-z', '0.12'])

    def spawner(name):
        return Node(package='controller_manager', executable='spawner', output='screen',
                    arguments=[name, '--param-file', controllers_yaml])

    jsb = spawner('joint_state_broadcaster')
    wheels = spawner('wheel_velocity_controller')
    steer = spawner('steer_position_controller')

    # jsb after the model spawns; the two command controllers after jsb.
    load_jsb = RegisterEventHandler(
        OnProcessExit(target_action=spawn, on_exit=[TimerAction(period=2.0, actions=[jsb])]))
    load_ctrls = RegisterEventHandler(
        OnProcessExit(target_action=jsb, on_exit=[wheels, steer]))

    # --- Phase 1 localization: wheel odometry + EKF (odom->base_link TF) ---
    wheel_odom = Node(
        package='friday_locomotion', executable='wheel_odometry', output='screen',
        parameters=[{'use_sim_time': True}])
    ekf = Node(
        package='robot_localization', executable='ekf_node',
        name='ekf_filter_node', output='screen',
        parameters=[os.path.join(pkg, 'config', 'ekf.yaml')])

    return LaunchDescription([
        DeclareLaunchArgument('world', default_value='empty_ground.sdf',
                              description='world file in friday_description/worlds'),
        DeclareLaunchArgument('headless', default_value='true',
                              description='true = server only; false = open the Gazebo GUI'),
        gz_headless, gz_gui, rsp, bridge, spawn, load_jsb, load_ctrls , wheel_odom, ekf,
    ])
