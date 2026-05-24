<<<<<<< HEAD
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
=======
import json
from csv import DictWriter
from io import StringIO

from arcane_eyes.services.cache_service import CAMERA_CACHE_HEADER, parse_camera_cache, serialize_camera_cache


def test_empty_cache_returns_empty_list():
    assert parse_camera_cache("") == []


def test_legacy_cache_migrates_to_current_format():
    entries = parse_camera_cache("id,ip,display_name\n1,192.168.100.25,Gate\n")

    assert len(entries) == 1
    assert entries[0].ip == "192.168.100.25"
    assert entries[0].capability.stale is True

    serialized = serialize_camera_cache(entries)
    assert serialized.splitlines()[0] == ",".join(CAMERA_CACHE_HEADER)


def test_current_cache_with_valid_capability_json_round_trips():
    capability = {
        "device_info": {"manufacturer": "EYEPLUS"},
        "profiles": [
            {
                "token": "Profile_1",
                "name": "mainStream",
                "uri": "rtsp://192.168.100.25:554/0/av0",
                "valid": True,
                "video": {"kind": "video", "codec": "hevc", "width": 1920, "height": 1080},
                "audio": {"kind": "audio", "codec": "pcm_alaw"},
            }
        ],
        "ptz_supported": True,
        "stale": False,
    }
    buffer = StringIO()
    writer = DictWriter(buffer, fieldnames=CAMERA_CACHE_HEADER, lineterminator="\n")
    writer.writeheader()
    writer.writerow({
        "id": 1,
        "ip": "192.168.100.25",
        "display_name": "Gate",
        "username": "",
        "password": "",
        "capability_json": json.dumps(capability),
        "selected_preview_profile": "",
        "selected_detail_profile": "",
        "cache_version": "2",
        "updated_at": "",
    })

    entries = parse_camera_cache(buffer.getvalue())

    assert len(entries) == 1
    assert entries[0].capability.device_info["manufacturer"] == "EYEPLUS"
    assert entries[0].capability.valid_profiles()[0].video.codec == "hevc"


def test_malformed_capability_json_marks_row_stale():
    row = ",".join(CAMERA_CACHE_HEADER) + "\n"
    row += '1,192.168.100.25,Gate,,,not-json,,,,\n'

    entries = parse_camera_cache(row)

    assert len(entries) == 1
    assert entries[0].capability.stale is True
    assert entries[0].capability.warnings


def test_duplicate_ips_rejected():
    serialized = "id,ip,display_name\n1,192.168.100.25,Gate\n2,192.168.100.25,Gate 2\n"

    assert parse_camera_cache(serialized) == []
>>>>>>> 890d149 (ONVIF Enhanced Camera Probing)
