from setuptools import find_packages, setup

package_name = 'friday_telemetry'

setup(
    name=package_name,
    version='0.3.0',
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
    description='Telemetry Command Node agent — the Command Center boundary.',
    license='Proprietary',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'telemetry_agent = friday_telemetry.telemetry_agent_node:main',
            'mock_command_center = friday_telemetry.mock_command_center:main',
        ],
    },
)
