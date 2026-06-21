"""Unit tests for the durable nonce floor (no ROS runtime)."""

from friday_module_agent.nonce_store import NonceStore


def test_inmemory_tracks_floor():
    s = NonceStore()
    assert s.last('A') is None
    s.commit('A', 5)
    assert s.last('A') == 5


def test_floor_is_per_source():
    s = NonceStore()
    s.commit('A', 5)
    s.commit('B', 2)
    assert s.last('A') == 5 and s.last('B') == 2


def test_persists_across_reload(tmp_path):
    p = str(tmp_path / 'nonces.json')
    s = NonceStore(p)
    s.commit('OP-001', 7)
    s.commit('OP-002', 3)
    # simulate a process restart: a fresh store on the same path
    reborn = NonceStore(p)
    assert reborn.last('OP-001') == 7
    assert reborn.last('OP-002') == 3


def test_reload_after_higher_commit(tmp_path):
    p = str(tmp_path / 'nonces.json')
    NonceStore(p).commit('OP-001', 1)
    s = NonceStore(p)
    s.commit('OP-001', 9)
    assert NonceStore(p).last('OP-001') == 9   # the latest floor survives


def test_missing_file_starts_empty(tmp_path):
    assert NonceStore(str(tmp_path / 'does-not-exist.json')).last('A') is None
