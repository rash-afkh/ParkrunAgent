from parkrun_agent.core.geo import GeoPoint, bounding_box, haversine_km

LONDON = GeoPoint(51.5074, -0.1278)
PARIS = GeoPoint(48.8566, 2.3522)


def test_haversine_known_distance():
    # London <-> Paris is ~343 km.
    assert 330 < haversine_km(LONDON, PARIS) < 360


def test_haversine_symmetric_and_zero():
    assert haversine_km(LONDON, LONDON) == 0
    assert abs(haversine_km(LONDON, PARIS) - haversine_km(PARIS, LONDON)) < 1e-9


def test_bounding_box_contains_points_within_radius():
    center = GeoPoint(54.6872, 25.2797)  # Vilnius
    radius = 50
    min_lat, max_lat, min_lon, max_lon = bounding_box(center, radius)
    # A point ~40 km north should be inside the box.
    near = GeoPoint(center.lat + 0.36, center.lon)
    assert haversine_km(center, near) < radius
    assert min_lat <= near.lat <= max_lat
    assert min_lon <= near.lon <= max_lon
