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
    AppendEnvironmentVariable,
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
                  arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
                             '/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
                             '/imu@sensor_msgs/msg/Imu[gz.msgs.IMU',
                             '/lidar3d/points@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked',
                             '/depthcam/points@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked',
                             '/gps/fix@sensor_msgs/msg/NavSatFix[gz.msgs.NavSat'])
    spawn = Node(package='ros_gz_sim', executable='create', output='screen',
                 arguments=['-topic', 'robot_description', '-name', 'mark1',
                            '-x', LaunchConfiguration('spawn_x'),
                            '-y', LaunchConfiguration('spawn_y'),
                            '-z', LaunchConfiguration('spawn_z')])

    def spawner(name):
        return Node(package='controller_manager', executable='spawner', output='screen',
                    arguments=[name, '--param-file', controllers_yaml])

    jsb = spawner('joint_state_broadcaster')
    wheels = spawner('wheel_velocity_controller')
    steer = spawner('steer_position_controller')
    load_jsb = RegisterEventHandler(
        OnProcessExit(target_action=spawn, on_exit=[TimerAction(period=20.0, actions=[jsb])]))
    load_ctrls = RegisterEventHandler(
        OnProcessExit(target_action=jsb, on_exit=[wheels, steer]))

    # ---- the real OS ----
    core = Node(package='friday_core_hub', executable='core_hub', name='core_hub',
                output='screen',
                parameters=[{'managed_nodes': ['locomotion=MARK1-LOCO-001',
                                               # telemetry only exists with tlm:=true;
                                               # when absent the supervisor just waits.
                                               'telemetry=MARK1-TLM-001'],
                             'autostart_delay_s': 10.0}])
    loco = Node(package='friday_locomotion', executable='locomotion_agent', name='locomotion',
                output='screen',
                parameters=[{'wheel_cmd_topic': WHEEL_CMD, 'steer_cmd_topic': STEER_CMD,
                             'safe_stop_timeout_s': 0.6}])

    # --- Phase 1 localization: wheel odometry + EKF (odom->base_link TF) ---
    wheel_odom = Node(
        package='friday_locomotion', executable='wheel_odometry', output='screen',
        parameters=[{'use_sim_time': True}])
    ekf = Node(
        package='robot_localization', executable='ekf_node',
        name='ekf_filter_node', output='screen',
        parameters=[os.path.join(pkg, 'config', 'ekf.yaml')])

    # --- GPS global anchor: navsat_transform_node (opt-in with gps:=true, default true).
    # Subscribes /gps/fix + /odometry/filtered + /imu, broadcasts utm->map TF so
    # a lat/lon can be converted to the map frame. Keeps the local EKF (ekf.yaml)
    # intact: this is an additive anchor layer only.
    gps_cond = IfCondition(LaunchConfiguration('gps'))
    navsat_yaml = os.path.join(pkg, 'config', 'navsat_transform.yaml')
    navsat = Node(
        package='robot_localization', executable='navsat_transform_node',
        name='navsat_transform', output='screen',
        parameters=[navsat_yaml],
        remappings=[('imu', '/imu'), ('gps/fix', '/gps/fix'),
                    ('odometry/filtered', '/odometry/filtered')],
        condition=gps_cond)

    # --- Phase 2 mapping: slam_toolbox (opt-in with slam:=true) ---
    slam = Node(
        package='slam_toolbox', executable='async_slam_toolbox_node',
        name='slam_toolbox', output='screen',
        parameters=[os.path.join(pkg, 'config', 'slam.yaml')],
        condition=IfCondition(LaunchConfiguration('slam')))
    slam_lifecycle = Node(
        package='nav2_lifecycle_manager', executable='lifecycle_manager',
        name='lifecycle_manager_slam', output='screen',
        parameters=[{'use_sim_time': True, 'autostart': True,
                     'node_names': ['slam_toolbox']}],
        condition=IfCondition(LaunchConfiguration('slam')))

    # --- Phase 3+4: Nav2 under the authority chain (opt-in with nav:=true) ---
    nav2_yaml = os.path.join(pkg, 'config', 'nav2.yaml')
    nav_cond = IfCondition(LaunchConfiguration('nav'))
    # NOTE: no use_sim_time — expires_at must live in the same WALL clock
    # domain the core/loco authority chain validates against.
    nav_adapter = Node(
        package='friday_locomotion', executable='nav_motion_adapter',
        output='screen', condition=nav_cond)
    nav_nodes = [
        Node(package='nav2_controller', executable='controller_server',
             output='screen', parameters=[nav2_yaml],
             remappings=[('cmd_vel', '/cmd_vel_nav')], condition=nav_cond),
        Node(package='nav2_planner', executable='planner_server',
             output='screen', parameters=[nav2_yaml], condition=nav_cond),
        Node(package='nav2_behaviors', executable='behavior_server',
             output='screen', parameters=[nav2_yaml],
             remappings=[('cmd_vel', '/cmd_vel_nav')], condition=nav_cond),
        Node(package='nav2_bt_navigator', executable='bt_navigator',
             output='screen', parameters=[nav2_yaml], condition=nav_cond),
        Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
             name='lifecycle_manager_navigation', output='screen',
             parameters=[{'use_sim_time': True, 'autostart': True,
                          'node_names': ['controller_server', 'planner_server',
                                         'behavior_server', 'bt_navigator']}],
             condition=nav_cond),
    ]

    # let gz resolve package://friday_description/meshes/* (visual meshes)
    mesh_env = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH', os.path.join(pkg, '..'))

    # --- sim -> FCC telemetry (opt-in with tlm:=true): the REAL telemetry
    # agent, signing as the distinct rover identity MARK1-SIM-001 so the sim
    # can never be mistaken for hardware. Secrets live in .sim-secrets/
    # (gitignored) at the workspace root -> /ws inside the container.
    tlm_agent = Node(
        package='friday_telemetry', executable='telemetry_agent',
        name='telemetry', output='screen',
        parameters=[{'rover_id': 'MARK1-SIM-001',
                     'mqtt_host': '192.168.1.6', 'mqtt_port': 8883,
                     'mqtt_tls': True,
                     'mqtt_ca': '/ws/.sim-secrets/ca.crt',
                     'mqtt_cert': '/ws/.sim-secrets/sim-rover.crt',
                     'mqtt_key': '/ws/.sim-secrets/sim-rover.key',
                     'mqtt_client_id': 'MARK1-SIM-001',
                     'rover_key_file': '/ws/.sim-secrets/rover_signing.key',
                     'operators_file': '/ws/.sim-secrets/operators.json',
                     'nonce_store': '/tmp/sim_tlm_nonce.json',
                     'tf_use_sim_time': True}],
        condition=IfCondition(LaunchConfiguration('tlm')))

    return LaunchDescription([
        mesh_env,
        DeclareLaunchArgument('tlm', default_value='false',
                              description='true = sign + radio sim telemetry to the FCC broker'),
        DeclareLaunchArgument('nav', default_value='false',
                              description='true = Nav2 autonomy (needs slam:=true)'),
        DeclareLaunchArgument('slam', default_value='false',
                              description='true = run slam_toolbox mapping'),
        DeclareLaunchArgument('gps', default_value='true',
                              description='true = navsat_transform_node (GPS->map anchor)'),
        DeclareLaunchArgument('world', default_value='empty_ground.sdf'),
        DeclareLaunchArgument('spawn_x', default_value='0.0'),
        DeclareLaunchArgument('spawn_y', default_value='0.0'),
        DeclareLaunchArgument('spawn_z', default_value='0.12'),
        DeclareLaunchArgument('headless', default_value='true'),
        gz_headless, gz_gui, rsp, bridge, spawn, load_jsb, load_ctrls, core, loco,
        wheel_odom, ekf, navsat, slam, slam_lifecycle, nav_adapter, *nav_nodes, tlm_agent,
    ])
