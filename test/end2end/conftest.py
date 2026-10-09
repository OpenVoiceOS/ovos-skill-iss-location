"""Shared end2end test fixtures for ovos-skill-iss-location.

``SatellitePredictions`` (in ``ovos_skill_iss_location.__init__``) loads
satellite TLE data through skyfield's ``load.tle_file``, which treats any
URL string without a ``://`` scheme as a local filesystem path and simply
opens it -- no network involved. Pointing ``STATIONS_URL`` at the vendored
fixture below exercises the same TLE parsing and pass-prediction logic the
skill uses at runtime, without depending on celestrak.org being reachable.
"""
from pathlib import Path

import pytest

from ovos_skill_iss_location import SatellitePredictions

FIXTURE_TLE = str(Path(__file__).parent / "fixtures" / "celestrak_stations.tle")


@pytest.fixture(autouse=True)
def _local_stations_fixture(monkeypatch):
    monkeypatch.setattr(SatellitePredictions, "STATIONS_URL", FIXTURE_TLE)
    yield
