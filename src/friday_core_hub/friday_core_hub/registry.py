"""Pure module-registry logic — no ROS dependencies, fully unit-testable.

Tracks registered modules and enforces the major-version registration rule
from the interface contract. The ROS-facing node (core_hub_node) wraps this.
"""

from dataclasses import dataclass

from friday_module_agent.protocol import major_compatible


@dataclass(frozen=True)
class ModuleRecord:
    """An accepted module's registration record (immutable)."""

    module_id: str
    hardware_type: str
    sw_version: str
    fw_version: str
    capabilities: tuple
    protocol_major: int
    protocol_minor: int
    protocol_patch: int
    namespace: str


@dataclass(frozen=True)
class RegistrationResult:
    accepted: bool
    assigned_namespace: str
    reason: str


class ModuleRegistry:
    """In-memory registry of module agents. Immutable-update internals."""

    def __init__(self):
        self._modules = {}            # module_id -> ModuleRecord

    def register(self, *, module_id, hardware_type, sw_version, fw_version,
                 capabilities, protocol_major, protocol_minor,
                 protocol_patch) -> RegistrationResult:
        if not module_id:
            return RegistrationResult(False, '', 'empty module_id')
        if not hardware_type:
            return RegistrationResult(False, '', 'empty hardware_type')
        if not major_compatible(protocol_major):
            return RegistrationResult(
                False, '',
                f'protocol major mismatch: agent reports major {protocol_major}')
        namespace = f'/mark1/{hardware_type}'
        record = ModuleRecord(
            module_id=module_id, hardware_type=hardware_type,
            sw_version=sw_version, fw_version=fw_version,
            capabilities=tuple(capabilities),
            protocol_major=protocol_major, protocol_minor=protocol_minor,
            protocol_patch=protocol_patch, namespace=namespace)
        # immutable update: build a new dict rather than mutating in place
        self._modules = {**self._modules, module_id: record}
        return RegistrationResult(True, namespace, 'registered')

    def is_registered(self, module_id: str) -> bool:
        return module_id in self._modules

    def get(self, module_id: str):
        return self._modules.get(module_id)

    @property
    def modules(self) -> dict:
        return dict(self._modules)
