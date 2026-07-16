"""Registry snapshot parsing -- pure, no ROS, fully unit-testable.

The Core Hub exports its registry to /var/lib/friday/registry.json for the
FCC. That same snapshot doubles as the persistence record: on startup the
hub restores every module it previously knew, marked DEAD-until-heard (we
never fake a liveness we have not observed -- real heartbeats promote them
back within seconds). This module owns the untrusted half of that: parsing
a snapshot that may be missing, truncated, corrupt, or hand-edited.

Reject-don't-repair: a malformed entry is skipped, never guessed at; a
malformed file restores nothing. The hub must boot fine either way.
"""

import json
import re

_PROTOCOL_RE = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')


def _parse_entry(m):
    """One snapshot entry -> kwargs for ModuleRegistry.register(), or None."""
    if not isinstance(m, dict):
        return None
    module_id = m.get('module_id')
    hardware_type = m.get('hardware_type')
    if not isinstance(module_id, str) or not module_id:
        return None
    if not isinstance(hardware_type, str) or not hardware_type:
        return None
    proto = _PROTOCOL_RE.match(m.get('protocol', '') or '')
    if proto is None:
        return None
    caps = m.get('capabilities')
    if not isinstance(caps, list) or not all(isinstance(c, str) for c in caps):
        return None
    sw = m.get('sw_version'); fw = m.get('fw_version')
    return {
        'module_id': module_id,
        'hardware_type': hardware_type,
        'sw_version': sw if isinstance(sw, str) else '',
        'fw_version': fw if isinstance(fw, str) else '',
        'capabilities': caps,
        'protocol_major': int(proto.group(1)),
        'protocol_minor': int(proto.group(2)),
        'protocol_patch': int(proto.group(3)),
    }


def parse_snapshot(text: str) -> list:
    """Snapshot file text -> list of register() kwargs (bad entries skipped)."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    modules = data.get('modules')
    if not isinstance(modules, list):
        return []
    parsed = (_parse_entry(m) for m in modules)
    return [e for e in parsed if e is not None]
