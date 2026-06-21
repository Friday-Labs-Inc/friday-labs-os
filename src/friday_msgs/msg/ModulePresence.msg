# Registry presence broadcast — emitted when a module registers or drops.
# Topic: /mark1/system/presence   QoS profile: state_default
# Owner: module-registry.
Mark1Header header               # header.module_id identifies the module
bool online                      # true on register, false on declared-dead
