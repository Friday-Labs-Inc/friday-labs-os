"""Tests for registry snapshot parsing (restore-on-boot path)."""

import json

from friday_core_hub.persistence import parse_snapshot


def _snap(**overrides):
    entry = {'module_id': 'MARK1-MOB-DRIVE-001', 'hardware_type': 'locomotion',
             'sw_version': '0.1.0', 'fw_version': '0.1.0',
             'capabilities': ['locomotion'], 'namespace': '/mark1/locomotion',
             'protocol': '0.1.0', 'liveness': 'OK', 'heartbeat_age_s': 0.1}
    entry.update(overrides)
    return json.dumps({'updated_unix': 123.0, 'modules': [entry]})


def test_happy_path_roundtrip():
    out = parse_snapshot(_snap())
    assert len(out) == 1
    e = out[0]
    assert e['module_id'] == 'MARK1-MOB-DRIVE-001'
    assert e['hardware_type'] == 'locomotion'
    assert e['capabilities'] == ['locomotion']
    assert (e['protocol_major'], e['protocol_minor'], e['protocol_patch']) == (0, 1, 0)


def test_corrupt_json_restores_nothing():
    assert parse_snapshot('{"modules": [truncat') == []
    assert parse_snapshot('') == []
    assert parse_snapshot('[1,2,3]') == []
    assert parse_snapshot('"a string"') == []


def test_missing_or_bad_fields_skip_that_entry_only():
    good = json.loads(_snap())['modules'][0]
    bad_id = {**good, 'module_id': ''}
    bad_type = {**good, 'hardware_type': None}
    bad_proto = {**good, 'protocol': 'not-semver'}
    bad_caps = {**good, 'capabilities': 'locomotion'}   # not a list
    snap = json.dumps({'modules': [bad_id, good, bad_type, bad_proto, bad_caps]})
    out = parse_snapshot(snap)
    assert len(out) == 1                     # only the good one survives
    assert out[0]['module_id'] == good['module_id']


def test_non_string_versions_degrade_to_empty():
    out = parse_snapshot(_snap(sw_version=None, fw_version=123))
    assert out[0]['sw_version'] == '' and out[0]['fw_version'] == ''


def test_modules_not_a_list():
    assert parse_snapshot(json.dumps({'modules': {'a': 1}})) == []
