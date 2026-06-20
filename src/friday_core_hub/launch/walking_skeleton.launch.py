"""Walking-skeleton bring-up: Core Hub + the Locomotion agent stub.

  ros2 launch friday_core_hub walking_skeleton.launch.py

The Core Hub starts, then its lifecycle supervisor configures and activates the
managed module(s). Each module registers and begins heartbeating; the hub logs
registration and liveness. This is Stage 2 (lifecycle orchestration) of the
seven-stage sim bring-up — no Gazebo required.
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    core_hub = Node(
        package='friday_core_hub',
        executable='core_hub',
        name='core_hub',
        output='screen',
        parameters=[{
            'managed_nodes': ['locomotion'],
            'autostart_delay_s': 3.0,
        }],
    )
    locomotion = Node(
        package='friday_locomotion',
        executable='locomotion_agent',
        name='locomotion',
        output='screen',
    )
    return LaunchDescription([core_hub, locomotion])
