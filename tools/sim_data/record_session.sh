#!/usr/bin/env bash
# Record one learned-perception data session in Gazebo (run INSIDE friday-os:sim,
# workspace built at /ws). Brings up the real OS (sim_os), the Nav2 motion
# adapter (the only path to the wheels), the data driver, and a rosbag.
#
#   tools/sim_data/record_session.sh <world.sdf> <minutes> <seed> <out_dir>
#   e.g. tools/sim_data/record_session.sh baylands.sdf 10 1 /data/bags
#   HEADLESS=false shows the Gazebo window (container needs DISPLAY + /tmp/.X11-unix)
#
# Output: <out_dir>/<world>_s<seed>/ (MCAP rosbag)
set -euo pipefail
WORLD=${1:-bumpy.sdf}; MINUTES=${2:-10}; SEED=${3:-0}; OUT=${4:-/data/bags}
NAME="${WORLD%.sdf}_s${SEED}"
set +u; source /opt/ros/jazzy/setup.bash; source /ws/install/setup.bash; set -u   # ROS setup scripts read unset vars
mkdir -p "$OUT"

ros2 launch friday_description sim_os.launch.py world:="$WORLD" headless:="${HEADLESS:-true}" terrain:=true gps:=false &
SIM=$!; ADAPTER=""; BAG=""
trap 'kill $SIM $ADAPTER $BAG 2>/dev/null || true; wait 2>/dev/null || true' EXIT
sleep 45   # gz up, controllers spawned (20 s delay), core autostart (10 s), lease issued

# refuse to record a rover that cannot move: both drive controllers must be active
for _ in $(seq 1 30); do
  ACTIVE=$(ros2 control list_controllers 2>/dev/null | grep -cE "(wheel_velocity|steer_position)_controller.*active" || true)
  [ "$ACTIVE" -ge 2 ] && break
  sleep 3
done
if [ "${ACTIVE:-0}" -lt 2 ]; then
  echo "ABORT: drive controllers not active after 90 s; not recording" >&2
  exit 1
fi

ros2 run friday_locomotion nav_motion_adapter &
ADAPTER=$!

# inputs (camera, depth, 2D scan), teacher input (3D LiDAR), label sources
# (geometric terrain map, ground-truth pose, odometry, what was commanded)
ros2 bag record -s mcap -o "$OUT/$NAME" \
  /depthcam/image /depthcam/depth_image /depthcam/camera_info \
  /scan /lidar3d/points /ground_scan/points /imu \
  /terrain/costmap /odometry/filtered /odom /model/mark1/pose \
  /cmd_vel_nav /mark1/locomotion/cmd_motion /mark1/contacts /tf /tf_static &
BAG=$!
sleep 3

python3 /ws/tools/sim_data/data_driver.py --minutes "$MINUTES" --seed "$SEED"
sleep 2
echo "recorded $OUT/$NAME"
