# Friday Labs OS dev / build image — ROS 2 Jazzy on Ubuntu 24.04.
# Gazebo Harmonic + ros_gz are added when sim bring-up (Stage 1+) lands;
# the walking skeleton (Stage 2, lifecycle orchestration) needs none of it.
FROM ros:jazzy-ros-base

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      python3-dev \
      python3-colcon-common-extensions \
      python3-pytest \
      python3-flake8 \
      ros-jazzy-rosidl-default-generators \
      ros-jazzy-lifecycle-msgs \
      ros-jazzy-launch \
      ros-jazzy-launch-ros \
      ros-jazzy-rosbag2-storage-mcap \
      git \
      mosquitto \
      mosquitto-clients \
      python3-paho-mqtt \
      python3-cbor2 \
      python3-cryptography \
    && rm -rf /var/lib/apt/lists/*

# Source ROS (and the workspace overlay, once built) for any interactive shell.
# The base image already provides a non-root `ubuntu` user (uid 1000) for
# VS Code dev containers; builds on the Legion farm run as root.
RUN echo "source /opt/ros/jazzy/setup.bash" >> /etc/bash.bashrc \
    && echo "[ -f /ws/install/setup.bash ] && source /ws/install/setup.bash" \
       >> /etc/bash.bashrc

WORKDIR /ws
CMD ["bash"]
