# Fault / security event reported by a module to fault-manager.
# Topic: /mark1/<module>/fault   QoS profile: state_default
# Owner: fault-manager.
uint8 SEVERITY_INFO     = 0
uint8 SEVERITY_WARN     = 1
uint8 SEVERITY_ERROR    = 2
uint8 SEVERITY_CRITICAL = 3

uint8 CATEGORY_GENERAL         = 0
uint8 CATEGORY_SECURITY_AUTH   = 1   # bad/forged signature, unknown operator
uint8 CATEGORY_SECURITY_REPLAY = 2   # nonce <= last seen (replayed command)
uint8 CATEGORY_COMMS           = 3   # link / transport failure

Mark1Header header
uint8  severity
uint8  category
uint32 fault_code
string description
string recommended_action
