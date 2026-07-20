from setuptools import setup

package_name = 'friday_terrain'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/terrain.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Friday Labs',
    maintainer_email='friday@friday-labs.example',
    description='Terrain intelligence: ground-scan -> traversability -> Nav2',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'terrain_analysis = friday_terrain.terrain_analysis_node:main',
        ],
    },
)
