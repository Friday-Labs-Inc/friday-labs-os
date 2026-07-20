"""Launch just the terrain analysis node (or combine into sim_os.launch.py)."""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        Node(
            package='friday_terrain',
            executable='terrain_analysis',
            name='terrain_analysis',
            output='screen',
        )
    ])
