"""Backup-attitude math (pure). Fixtures are REAL bytes from the OnePlus 6T
(HyperIMU 63-field CSV, captured 2026-07-17): accel@0-2, mag@3-5, gyro@9-11."""
import math

import pytest

from friday_phone_bridge import attitude
from friday_phone_bridge.ingest import parse_imu_datagram

# a genuine packet, phone at rest on a desk
REAL = (b"0.012861421,1.6606189,9.650553,-39.318752,-47.775,-11.55,139.20187,"
        b"-9.800829,0.15680683,-1.5271181E-4,0.0056503373,0.0015271181,0.0,0.0,"
        b"0.0,0.0,255.0,0.0,0.026329473,1.6689296,9.663558,-0.008433655,"
        b"-0.03309977,-0.0025720596,0.028497227,-0.08054213,-0.93382,-9.95625,"
        b"-173.38126,186.31876,-1.5271181E-4,0.0056503373,0.0015271181,0.0,0.0,"
        b"0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.028208282,-0.08074811,-0.93304336,0.0,"
        b"0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.024825536,1.6438692,"
        b"9.61466,3148.0,642.0,352.0")


def test_real_packet_yields_mag_when_index_given():
    s = parse_imu_datagram(REAL, accel_i=0, gyro_i=9, mag_i=3)
    assert s is not None
    assert s.az == pytest.approx(9.650553)
    assert (s.mx, s.my, s.mz) == pytest.approx((-39.318752, -47.775, -11.55))


def test_mag_absent_when_index_not_configured():
    s = parse_imu_datagram(REAL, accel_i=0, gyro_i=9)
    assert s is not None and s.mx is None and s.my is None and s.mz is None


def test_implausible_mag_is_dropped_but_sample_survives():
    # a magnet on the pod: 400 uT is not Earth's field
    line = b"0.0,0.0,9.8,400.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0"
    s = parse_imu_datagram(line, accel_i=0, gyro_i=9, mag_i=3)
    assert s is not None and s.mx is None      # heading unknown, tilt still usable
    assert s.az == 9.8


def test_tilt_flat_and_on_its_side():
    assert attitude.tilt_deg(0.0, 0.0, 9.81) == pytest.approx(0.0, abs=0.01)
    assert attitude.tilt_deg(9.81, 0.0, 0.0) == pytest.approx(90.0, abs=0.01)
    assert attitude.tilt_deg(0.0, 0.0, -9.81) == pytest.approx(180.0, abs=0.01)


def test_tilt_none_when_gravity_unusable():
    assert attitude.tilt_deg(0.0, 0.0, 0.0) is None          # free fall
    assert attitude.tilt_deg(30.0, 30.0, 30.0) is None       # hard accel


def test_tilt_on_the_real_packet():
    s = parse_imu_datagram(REAL, accel_i=0, gyro_i=9, mag_i=3)
    assert attitude.tilt_deg(s.ax, s.ay, s.az) == pytest.approx(9.76, abs=0.1)


def test_vibration_zero_at_rest_and_grows_with_shaking():
    at_rest = attitude.vibration_rms([(0.0, 0.0, 9.80665)] * 5)
    assert at_rest == pytest.approx(0.0, abs=1e-6)
    shaking = attitude.vibration_rms([(0.0, 0.0, 12.0), (0.0, 0.0, 7.5)] * 3)
    assert shaking > 2.0
    assert attitude.vibration_rms([]) is None


def test_heading_cardinal_directions_when_flat():
    # flat phone, mag pointing +x = north -> heading 0
    assert attitude.heading_deg(0, 0, 9.81, 30.0, 0.0, 0.0) == pytest.approx(0.0, abs=0.5)
    # mag along -y -> east (90)
    assert attitude.heading_deg(0, 0, 9.81, 0.0, -30.0, 0.0) == pytest.approx(90.0, abs=0.5)


def test_heading_is_tilt_compensated():
    """Same physical heading, phone pitched 30 deg — heading must not swing."""
    p = math.radians(30.0)
    g, m = 9.81, 30.0
    flat = attitude.heading_deg(0, 0, g, m, 0.0, 0.0)
    # rotate BOTH gravity and the field vector about the y-axis by pitch
    ax, az = -g * math.sin(p), g * math.cos(p)
    mx, mz = m * math.cos(p), -m * math.sin(p)
    pitched = attitude.heading_deg(ax, 0, az, mx, 0.0, mz)
    assert pitched == pytest.approx(flat, abs=1.0)


def test_heading_none_without_mag_or_gravity():
    assert attitude.heading_deg(0, 0, 9.81, None, None, None) is None
    assert attitude.heading_deg(0, 0, 0, 30.0, 0.0, 0.0) is None
