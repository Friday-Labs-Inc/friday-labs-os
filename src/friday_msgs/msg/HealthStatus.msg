# Periodic module health summary.
# Topic: /mark1/<module>/health   QoS profile: state_default
#   (RELIABLE, VOLATILE, KEEP_LAST 10)
# Owner: system-health-manager.
uint8 OVERALL_OK       = 0
uint8 OVERALL_DEGRADED = 1
uint8 OVERALL_FAULT    = 2

Mark1Header header
uint8   overall                  # one of OVERALL_*
uint8   power_state
float32 temperature_c
float32 cpu_load                 # 0.0 - 1.0
float32 mem_used_pct             # 0.0 - 100.0
float32 storage_used_pct         # 0.0 - 100.0
uint8   comms_status
uint32  last_error_code
uint64  uptime_s
string  detail
