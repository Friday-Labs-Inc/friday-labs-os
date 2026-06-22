"""Mark 1 Stage 1 — the FULL Command Center boundary driving the sim rover.

  ros2 launch friday_description sim_cc.launch.py \
      mqtt_host:=127.0.0.1 mqtt_port:=1893 operators_file:=/out/operators.json

This is `sim.launch.py` (physics + wheel/steer controllers) PLUS the real OS:
  * Core Hub  — authority lease + 20 Hz safety pulse + lifecycle supervisor,
  * Locomotion agent — authority enforcement + safe-stop + corner-steer kinematics,
  * Telemetry agent — the signed-CBOR-over-MQTT **Command Center boundary**.

End to end: an operator signs a MotionCommand, the Command Center publishes it to
`mark1/<rover>/cmd/motion` on the broker, the Telemetry agent VALIDATES it (Ed25519
signature + allowlist + monotonic nonce + expiry + rover_id), re-issues it AS the
authority holder on `/mark1/locomotion/cmd_motion`, and the physics rover drives —
while forged / expired / replayed commands are rejected and never executed.
Operator → Command Center → broker → rover → motion, all through the real OS.

Core supervises BOTH locomotion and telemetry. Set mqtt_tls:=true (+ ca/cert/key)
for the live mutual-TLS EMQX broker; the defaults use a plain local broker.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

WHEEL_CMD = '/wheel_velocity_controller/commands'
STEER_CMD = '/steer_position_controller/commands'


def generate_launch_description() -> LaunchDescription:
    pkg = get_package_share_directory('friday_description')

    sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(pkg, 'launch', 'sim.launch.py')),
        launch_arguments={'world': LaunchConfiguration('world'),
                          'headless': LaunchConfiguration('headless')}.items())

    core = Node(package='friday_core_hub', executable='core_hub', name='core_hub',
                output='screen',
                parameters=[{'managed_nodes': ['locomotion', 'telemetry'],
                             'autostart_delay_s': 10.0}])

    loco = Node(package='friday_locomotion', executable='locomotion_agent', name='locomotion',
                output='screen',
                parameters=[{'wheel_cmd_topic': WHEEL_CMD, 'steer_cmd_topic': STEER_CMD,
                             'safe_stop_timeout_s': 0.6}])

    tlm = Node(package='friday_telemetry', executable='telemetry_agent', name='telemetry',
               output='screen',
               parameters=[{
                   'rover_id': LaunchConfiguration('rover_id'),
                   'mqtt_host': LaunchConfiguration('mqtt_host'),
                   'mqtt_port': ParameterValue(LaunchConfiguration('mqtt_port'), value_type=int),
                   'mqtt_tls': ParameterValue(LaunchConfiguration('mqtt_tls'), value_type=bool),
                   'mqtt_ca': LaunchConfiguration('mqtt_ca'),
                   'mqtt_cert': LaunchConfiguration('mqtt_cert'),
                   'mqtt_key': LaunchConfiguration('mqtt_key'),
                   'mqtt_client_id': LaunchConfiguration('mqtt_client_id'),
                   'operators_file': LaunchConfiguration('operators_file'),
                   'nonce_store': LaunchConfiguration('nonce_store'),
               }])

    return LaunchDescription([
        DeclareLaunchArgument('world', default_value='empty_ground.sdf'),
        DeclareLaunchArgument('headless', default_value='true'),
        DeclareLaunchArgument('rover_id', default_value='MARK1-001'),
        DeclareLaunchArgument('mqtt_host', default_value='127.0.0.1'),
        DeclareLaunchArgument('mqtt_port', default_value='1883'),
        DeclareLaunchArgument('mqtt_tls', default_value='false'),
        DeclareLaunchArgument('mqtt_ca', default_value=''),
        DeclareLaunchArgument('mqtt_cert', default_value=''),
        DeclareLaunchArgument('mqtt_key', default_value=''),
        DeclareLaunchArgument('mqtt_client_id', default_value=''),
        DeclareLaunchArgument('operators_file', default_value=''),
        DeclareLaunchArgument('nonce_store', default_value=''),
        sim, core, loco, tlm,
    ])
