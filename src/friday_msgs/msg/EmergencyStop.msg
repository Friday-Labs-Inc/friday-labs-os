# Emergency stop — the DDS safe-stop path (<=500 ms publish-to-motors-off).
# Topic: /mark1/locomotion/emergency_stop   QoS profile: critical_reliable
# Owner: command-router / safety-supervisor. header.module_id = source.
# (Categories per friday_msgs Schema Conventions.)
uint8 CATEGORY_OPERATOR  = 0   # human-initiated via Command Center
uint8 CATEGORY_COLLISION = 1   # perception-detected, autonomy-initiated
uint8 CATEGORY_CASCADE   = 2   # downstream of another fault (power/comms loss)
uint8 CATEGORY_WATCHDOG  = 3   # firmware-level safe-stop, post-hoc reported
uint8 CATEGORY_TEST      = 4   # injected by fault-injection, not real

Mark1Header header
uint8  category
string reason
