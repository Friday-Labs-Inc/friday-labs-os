"""Unit tests for the pure module-registry logic (no ROS runtime needed)."""

from friday_core_hub.registry import ModuleRegistry
from friday_module_agent.protocol import PROTOCOL_MAJOR


def _reg(registry, module_id='MARK1-LOCO-001', hardware_type='locomotion',
         major=PROTOCOL_MAJOR):
    return registry.register(
        module_id=module_id, hardware_type=hardware_type,
        sw_version='0.1.0', fw_version='none',
        capabilities=['drive', 'steer'],
        protocol_major=major, protocol_minor=1, protocol_patch=0)


def test_register_accepts_matching_major():
    reg = ModuleRegistry()
    result = _reg(reg)
    assert result.accepted is True
    assert result.assigned_namespace == '/mark1/locomotion'
    assert reg.is_registered('MARK1-LOCO-001')


def test_register_rejects_major_mismatch():
    reg = ModuleRegistry()
    result = _reg(reg, major=PROTOCOL_MAJOR + 1)
    assert result.accepted is False
    assert 'major' in result.reason
    assert not reg.is_registered('MARK1-LOCO-001')


def test_register_rejects_empty_module_id():
    reg = ModuleRegistry()
    result = _reg(reg, module_id='')
    assert result.accepted is False


def test_register_is_idempotent_on_id():
    reg = ModuleRegistry()
    _reg(reg)
    _reg(reg)
    assert len(reg.modules) == 1
