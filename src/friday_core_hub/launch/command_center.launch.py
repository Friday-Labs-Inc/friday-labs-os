"""Full-system bring-up: Core Hub + Locomotion + the Command Center boundary.

  ros2 launch friday_core_hub command_center.launch.py \
       operators_file:=/tmp/operators.json mqtt_host:=127.0.0.1

The supervisor configures + activates both module agents. Telemetry connects to
the MQTT broker and starts validating inbound Command Center commands; valid
motion commands are republished to Locomotion (which drives and reports
odometry). Requires an MQTT broker (e.g. `mosquitto`) reachable at mqtt_host.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    operators_file = LaunchConfiguration('operators_file')
    mqtt_host = LaunchConfiguration('mqtt_host')
    rover_id = LaunchConfiguration('rover_id')
    return LaunchDescription([
        DeclareLaunchArgument('operators_file', default_value=''),
        DeclareLaunchArgument('mqtt_host', default_value='127.0.0.1'),
        DeclareLaunchArgument('rover_id', default_value='MARK1-001'),
        Node(
            package='friday_core_hub', executable='core_hub', name='core_hub',
            output='screen',
            parameters=[{
                'managed_nodes': ['locomotion', 'telemetry'],
                'autostart_delay_s': 3.0,
            }],
        ),
        Node(
            package='friday_locomotion', executable='locomotion_agent',
            name='locomotion', output='screen',
        ),
        Node(
            package='friday_telemetry', executable='telemetry_agent',
            name='telemetry', output='screen',
            parameters=[{
                'operators_file': operators_file,
                'mqtt_host': mqtt_host,
                'rover_id': rover_id,
            }],
        ),
    ])
