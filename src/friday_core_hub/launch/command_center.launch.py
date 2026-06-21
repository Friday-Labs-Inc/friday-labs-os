"""Full-system bring-up: Core Hub + Locomotion + the Command Center boundary.

  ros2 launch friday_core_hub command_center.launch.py \
       operators_file:=/tmp/operators.json record:=true

The supervisor configures + activates both module agents. Telemetry validates
inbound signed commands and re-issues valid ones to Locomotion AS the authority
lease holder; Locomotion enforces authority + nonce/expiry and runs the safe-stop
watchdog. With record:=true an MCAP recorder captures all /mark1 topics — this
seeds the fleet failure-data corpus (FaultReports etc. that can't be backfilled).
Requires an MQTT broker (e.g. `mosquitto`) reachable at mqtt_host.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    operators_file = LaunchConfiguration('operators_file')
    mqtt_host = LaunchConfiguration('mqtt_host')
    rover_id = LaunchConfiguration('rover_id')
    tlm_nonce_store = LaunchConfiguration('tlm_nonce_store')
    loco_nonce_store = LaunchConfiguration('loco_nonce_store')
    record = LaunchConfiguration('record')
    bag_dir = LaunchConfiguration('bag_dir')

    return LaunchDescription([
        DeclareLaunchArgument('operators_file', default_value=''),
        DeclareLaunchArgument('mqtt_host', default_value='127.0.0.1'),
        DeclareLaunchArgument('rover_id', default_value='MARK1-001'),
        DeclareLaunchArgument('tlm_nonce_store', default_value=''),
        DeclareLaunchArgument('loco_nonce_store', default_value=''),
        DeclareLaunchArgument('record', default_value='false'),
        DeclareLaunchArgument('bag_dir', default_value='/tmp/mark1_bag'),
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
            parameters=[{'nonce_store': loco_nonce_store}],
        ),
        Node(
            package='friday_telemetry', executable='telemetry_agent',
            name='telemetry', output='screen',
            parameters=[{
                'operators_file': operators_file,
                'mqtt_host': mqtt_host,
                'rover_id': rover_id,
                'nonce_store': tlm_nonce_store,
            }],
        ),
        # Failure-data corpus: record every /mark1 topic to MCAP (opt-in).
        ExecuteProcess(
            condition=IfCondition(record),
            cmd=['ros2', 'bag', 'record', '--storage', 'mcap',
                 '-o', bag_dir, '--regex', '/mark1/.*'],
            output='screen',
        ),
    ])
