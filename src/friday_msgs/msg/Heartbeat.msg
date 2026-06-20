# Liveness beacon published by every module agent at 5 Hz (200 ms).
# Topic: /mark1/<module>/heartbeat   QoS profile: heartbeat
#   (BEST_EFFORT, VOLATILE, KEEP_LAST 1, Deadline 500 ms, Liveliness lease 1 s)
# Owner: system-health-manager.
Mark1Header header
uint64 sequence                  # monotonic per module, from 0 at activate
uint8  lifecycle_state           # lifecycle_msgs/State PRIMARY_STATE_* value
