# celestrak_stations.tle

TLE (Two-Line Element) data for the active space-station satellite group.
Fetched once from [celestrak.org](https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle).

Used by the end2end tests to feed `SatellitePredictions` (the ISS pass
predictor in `ovos_skill_iss_location/__init__.py`) without a live request
to celestrak.org. Orbital elements go stale after a few weeks but remain
structurally valid TLE data, which is all the parsing and prediction code
under test needs.

CelesTrak states its data is public domain and freely redistributable for
any purpose. See the [GP data formats page](https://celestrak.org/NORAD/documentation/gp-data-formats.php)
and the [webmaster documentation](https://celestrak.org/webmaster/documentation.php)
for the current terms.
