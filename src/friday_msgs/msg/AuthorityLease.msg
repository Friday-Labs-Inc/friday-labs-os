# The rover-wide command-authority lease (Authority Lease Protocol).
# Topic: /mark1/system/authority   QoS profile: critical_reliable
# Owner: authority-lease-service (Core Hub by default; Telemetry on failover).
#
# Only `holder_module_id` may issue motion / recovery / emergency commands.
# Lease: 2 s duration, renewed every 500 ms, in-memory only. `epoch` increments
# on every lease transition; on a partition heal, the lower epoch stands down.
Mark1Header header
string holder_module_id
uint64 epoch
builtin_interfaces/Time expires_at
