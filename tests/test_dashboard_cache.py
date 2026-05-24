from arcane_eyes.main import (
    CameraCacheEntry,
    grid_position_for_feed,
    parse_camera_cache,
    serialize_camera_cache,
)


def test_parse_camera_cache_returns_empty_for_missing_or_empty_cache():
    assert parse_camera_cache("") == []
    assert parse_camera_cache("  \n ") == []


def test_parse_camera_cache_treats_missing_header_as_corrupted():
    assert parse_camera_cache("192.168.100.10,192.168.100.11") == []
    assert parse_camera_cache("ip,display_name\n192.168.100.10,Front Door\n") == []


def test_parse_camera_cache_treats_invalid_rows_as_corrupted():
    assert parse_camera_cache("id,ip,display_name\nx,192.168.100.10,Front Door\n") == []
    assert parse_camera_cache("id,ip,display_name\n0,192.168.100.10,Front Door\n") == []
    assert parse_camera_cache("id,ip,display_name\n1,not-an-ip,Front Door\n") == []
    assert parse_camera_cache("id,ip,display_name\n1,192.168.100.10,\n") == []


def test_parse_camera_cache_treats_duplicate_ids_or_ips_as_corrupted():
    assert parse_camera_cache(
        "id,ip,display_name\n1,192.168.100.10,Front Door\n1,192.168.100.11,Garage\n"
    ) == []
    assert parse_camera_cache(
        "id,ip,display_name\n1,192.168.100.10,Front Door\n2,192.168.100.10,Garage\n"
    ) == []


def test_parse_camera_cache_loads_valid_csv_ordered_by_id():
    entries = parse_camera_cache(
        "id,ip,display_name\n2,192.168.100.25,Living Room\n1,192.168.100.24,Front Door\n"
    )

    assert entries == [
        CameraCacheEntry(id=1, ip="192.168.100.24", display_name="Front Door"),
        CameraCacheEntry(id=2, ip="192.168.100.25", display_name="Living Room"),
    ]


def test_serialize_camera_cache_writes_required_header_ordered_by_id():
    serialized = serialize_camera_cache([
        CameraCacheEntry(id=2, ip="192.168.100.25", display_name="Living Room"),
        CameraCacheEntry(id=1, ip="192.168.100.24", display_name="Front Door"),
    ])

    assert serialized == (
        "id,ip,display_name\n"
        "1,192.168.100.24,Front Door\n"
        "2,192.168.100.25,Living Room\n"
    )


def test_clockwise_grid_slot_mapping():
    assert [grid_position_for_feed(index) for index in range(4)] == [
        (0, 0),
        (0, 1),
        (1, 1),
        (1, 0),
    ]
