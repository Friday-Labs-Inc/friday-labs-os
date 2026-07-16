"""Unit tests for the pure phone-ingest logic (no ROS runtime)."""

import json
import math

from friday_phone_bridge import ingest

# ---- IMU datagrams ---------------------------------------------------------

IMU_OK = {
    'LSM6DSO Accelerometer': [0.1, -0.2, 9.81],
    'LSM6DSO Gyroscope': [0.01, 0.02, -0.03],
    'Timestamp': 12345,
}


def _imu(payload) -> bytes:
    return json.dumps(payload).encode('utf-8')


def test_imu_valid_datagram_parses():
    s = ingest.parse_imu_datagram(_imu(IMU_OK))
    assert s == ingest.ImuSample(ax=0.1, ay=-0.2, az=9.81,
                                 gx=0.01, gy=0.02, gz=-0.03)


def test_imu_key_match_is_case_insensitive_and_chip_agnostic():
    s = ingest.parse_imu_datagram(_imu({
        'ICM-20602 ACCELEROMETER': [1, 2, 3],
        'icm-20602 gyroscope': [4, 5, 6]}))
    assert s is not None and s.az == 3.0 and s.gz == 6.0


def test_imu_rejects_non_json_and_non_dict():
    assert ingest.parse_imu_datagram(b'\xff\xfe garbage') is None
    assert ingest.parse_imu_datagram(b'not json') is None
    assert ingest.parse_imu_datagram(b'[1, 2, 3]') is None


def test_imu_rejects_missing_sensor():
    assert ingest.parse_imu_datagram(
        _imu({'LSM6DSO Accelerometer': [0, 0, 9.8]})) is None


def test_imu_rejects_short_or_non_numeric_triplet():
    assert ingest.parse_imu_datagram(_imu({
        'Accelerometer': [0, 9.8], 'Gyroscope': [0, 0, 0]})) is None
    assert ingest.parse_imu_datagram(_imu({
        'Accelerometer': ['a', 'b', 'c'], 'Gyroscope': [0, 0, 0]})) is None
    assert ingest.parse_imu_datagram(_imu({
        'Accelerometer': [True, False, True], 'Gyroscope': [0, 0, 0]})) is None


def test_imu_rejects_nan_and_inf():
    raw = b'{"Accelerometer": [0, 0, NaN], "Gyroscope": [0, 0, 0]}'
    assert ingest.parse_imu_datagram(raw) is None
    raw = b'{"Accelerometer": [0, 0, 9.8], "Gyroscope": [0, 0, Infinity]}'
    assert ingest.parse_imu_datagram(raw) is None


def test_imu_rejects_out_of_range():
    assert ingest.parse_imu_datagram(_imu({
        'Accelerometer': [0, 0, 999.0], 'Gyroscope': [0, 0, 0]})) is None
    assert ingest.parse_imu_datagram(_imu({
        'Accelerometer': [0, 0, 9.8], 'Gyroscope': [0, 0, -100.0]})) is None


# ---- gpsd TPV lines ---------------------------------------------------------

def _tpv(**over):
    base = {'class': 'TPV', 'mode': 3, 'lat': 13.0827, 'lon': 80.2707,
            'altHAE': 6.1, 'epx': 3.0, 'epy': 4.0, 'epv': 5.0}
    base.update(over)
    return json.dumps(base)


def test_fix_valid_tpv_parses():
    fix = ingest.parse_gpsd_line(_tpv())
    assert fix.latitude == 13.0827 and fix.longitude == 80.2707
    assert fix.altitude == 6.1
    assert fix.position_covariance == (9.0, 0.0, 0.0, 0.0, 16.0, 0.0, 0.0, 0.0, 25.0)
    assert fix.covariance_type == ingest.COVARIANCE_TYPE_APPROXIMATED


def test_fix_rejects_non_tpv_and_no_fix():
    assert ingest.parse_gpsd_line('{"class": "SKY"}') is None
    assert ingest.parse_gpsd_line(_tpv(mode=1)) is None      # no fix yet
    assert ingest.parse_gpsd_line('not json') is None


def test_fix_rejects_missing_or_out_of_range_position():
    assert ingest.parse_gpsd_line(_tpv(lat=None)) is None
    assert ingest.parse_gpsd_line(_tpv(lat=91.0)) is None
    assert ingest.parse_gpsd_line(_tpv(lon=-181.0)) is None


def test_fix_altitude_nan_is_allowed_for_2d_fix():
    fix = ingest.parse_gpsd_line(_tpv(mode=2, altHAE=None, alt=None))
    assert fix is not None and math.isnan(fix.altitude)
    assert fix.latitude == 13.0827                           # position still good


def test_fix_covariance_unknown_without_error_estimates():
    fix = ingest.parse_gpsd_line(_tpv(epx=None, epy=None, epv=None))
    assert fix.covariance_type == ingest.COVARIANCE_TYPE_UNKNOWN
    assert fix.position_covariance == (0.0,) * 9


def test_fix_vertical_error_falls_back_when_missing():
    fix = ingest.parse_gpsd_line(_tpv(epv=None))
    assert fix.covariance_type == ingest.COVARIANCE_TYPE_APPROXIMATED
    assert fix.position_covariance[8] == 10000.0


# ---- teleport rejection ------------------------------------------------------

def test_jump_suspicious_detects_teleport():
    prev = ingest.parse_gpsd_line(_tpv())
    near = ingest.parse_gpsd_line(_tpv(lat=13.09, lon=80.28))
    far = ingest.parse_gpsd_line(_tpv(lat=48.85, lon=2.35))  # Paris, not Chennai
    assert not ingest.jump_suspicious(prev, near)
    assert ingest.jump_suspicious(prev, far)


# ---- rate limiter ------------------------------------------------------------

def test_rate_allow_caps_within_window():
    win = ingest.RateWindow(window_start_s=100.0, count=0)
    for _ in range(3):
        win, allowed = ingest.rate_allow(win, 100.5, limit_per_s=3)
        assert allowed
    win, allowed = ingest.rate_allow(win, 100.9, limit_per_s=3)
    assert not allowed


def test_rate_allow_resets_on_new_window():
    win = ingest.RateWindow(window_start_s=100.0, count=3)
    win, allowed = ingest.rate_allow(win, 101.1, limit_per_s=3)
    assert allowed and win.count == 1


# ---- health ------------------------------------------------------------------

def test_health_ok_when_both_streams_fresh():
    assert ingest.health_from_ages(1.0, 0.5, 3.0, 1.0) == (ingest.HEALTH_OK, '')


def test_health_degraded_when_stale_or_never_received():
    overall, detail = ingest.health_from_ages(10.0, 0.5, 3.0, 1.0)
    assert overall == ingest.HEALTH_DEGRADED and 'gps' in detail
    overall, detail = ingest.health_from_ages(1.0, None, 3.0, 1.0)
    assert overall == ingest.HEALTH_DEGRADED and 'imu' in detail
    overall, detail = ingest.health_from_ages(None, None, 3.0, 1.0)
    assert 'gps' in detail and 'imu' in detail


def test_health_never_reports_fault():
    # Advisory sensor: worst case is DEGRADED, never FAULT.
    overall, _ = ingest.health_from_ages(None, None, 3.0, 1.0)
    assert overall == ingest.HEALTH_DEGRADED


# ---- HyperIMU CSV wire format (confirmed by live capture 2026-07-16) -------
def test_csv_accel_gyro_only():
    raw = b'-0.45,3.68,9.23,-0.13,-0.38,-0.17\r\n'
    s = ingest.parse_imu_datagram(raw)
    assert s is not None
    assert (s.ax, s.ay, s.az) == (-0.45, 3.68, 9.23)
    assert (s.gx, s.gy, s.gz) == (-0.13, -0.38, -0.17)


def test_csv_many_sensors_with_index_map():
    # real 24-field capture shape: accel at 0, gyro at 9 (mag/orientation between)
    fields = ['-0.45', '3.68', '9.23', '-35.9', '-1.8', '-8.75',
              '88.3', '-21.4', '-2.8', '-0.132', '-0.380', '-0.172'] + ['0.0'] * 12
    raw = (','.join(fields) + '\r\n').encode()
    s = ingest.parse_imu_datagram(raw, accel_i=0, gyro_i=9)
    assert s is not None and s.gz == -0.172


def test_csv_default_indices_reject_magnetometer_as_gyro():
    # all-sensors stream with defaults: field 3 is the magnetometer (~36 "rad/s"
    # would be absurd) -> the range gate rejects rather than publishing garbage
    raw = b'-0.45,3.68,9.23,-35.9,-1.8,-8.75,88.3\r\n'
    assert ingest.parse_imu_datagram(raw) is None


def test_csv_rejects_garbage():
    assert ingest.parse_imu_datagram(b'not,numbers,at,all,x,y\r\n') is None
    assert ingest.parse_imu_datagram(b'1.0,2.0\r\n') is None            # too few
    assert ingest.parse_imu_datagram(b'1,2,nan,4,5,6\r\n') is None      # non-finite
