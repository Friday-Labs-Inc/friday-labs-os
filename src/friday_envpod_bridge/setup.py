from setuptools import find_packages, setup

package_name = 'friday_envpod_bridge'

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
    description='Environmental sensor pod agent (SensorHub over WiFi, advisory only).',
    license='Proprietary',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'envpod_bridge = friday_envpod_bridge.envpod_bridge_node:main',
        ],
    },
)
