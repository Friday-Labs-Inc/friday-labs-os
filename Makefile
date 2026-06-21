# Friday Labs OS — workspace tasks. Run inside the ROS 2 Jazzy dev container
# (see .devcontainer/). Each target sources the ROS environment itself.
SHELL := /bin/bash
ROS_SETUP := /opt/ros/jazzy/setup.bash
WS_SETUP := install/setup.bash

.PHONY: help build test run lint clean

help:
	@echo "Targets: build | test | run | lint | clean"
	@echo "  build  colcon build --symlink-install"
	@echo "  test   colcon test + result summary"
	@echo "  run    ros2 launch friday_core_hub walking_skeleton.launch.py"
	@echo "  clean  remove build/ install/ log/"

build:
	source $(ROS_SETUP) && colcon build --symlink-install

test:
	source $(ROS_SETUP) && source $(WS_SETUP) && \
		colcon test && colcon test-result --verbose

run:
	source $(ROS_SETUP) && source $(WS_SETUP) && \
		ros2 launch friday_core_hub walking_skeleton.launch.py

lint:
	source $(ROS_SETUP) && colcon test --packages-select \
		friday_module_agent friday_core_hub friday_locomotion \
		--ctest-args -R flake8 || true

clean:
	rm -rf build install log
