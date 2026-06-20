import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'friday_core_hub'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Friday Labs Inc.',
    maintainer_email='iamfriday86@gmail.com',
    description='Core Compute Hub: registry, health monitor, lifecycle supervisor.',
    license='Proprietary',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'core_hub = friday_core_hub.core_hub_node:main',
        ],
    },
)
