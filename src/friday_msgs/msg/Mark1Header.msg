# Mark 1 mandatory protocol + identity header.
# Every Mark 1-specific message embeds this as its first field `header`.
# Packed semver (three fields) — one uint16 cannot carry major+minor+patch.
# module-registry compares protocol_major on registration.
# See docs/addendums/friday_msgs Schema Conventions.md
uint8  protocol_major
uint8  protocol_minor
uint16 protocol_patch
string module_id                 # canonical id, e.g. MARK1-LOCO-001
builtin_interfaces/Time stamp
