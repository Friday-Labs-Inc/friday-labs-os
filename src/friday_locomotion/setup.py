from setuptools import find_packages, setup

package_name = 'friday_locomotion'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Friday Labs Inc.',
    maintainer_email='iamfriday86@gmail.com',
    description='Locomotion Control Unit agent (walking-skeleton stub).',
    license='Proprietary',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'locomotion_agent = friday_locomotion.locomotion_agent_node:main',
            'wheel_odometry = friday_locomotion.wheel_odometry_node:main',
            'nav_motion_adapter = friday_locomotion.nav_motion_adapter:main',
        ],
    },
)
