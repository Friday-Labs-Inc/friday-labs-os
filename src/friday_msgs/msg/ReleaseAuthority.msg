# Announces that the current holder is standing down so a requester can take over.
# Topic: /mark1/system/authority_release   QoS profile: critical_reliable
# Owner: authority-lease-service. Published by Telemetry after it grants a
# RequestAuthority; the holder then stops issuing the lease + commands and a
# 500 ms quiet window precedes the requester acquiring at `epoch`+1.
# (See the Authority Lease Protocol addendum, "Authority Return".)
Mark1Header header
string releasing_module_id
uint64 epoch                       # the epoch being released (the new holder acquires at epoch+1)
string reason
