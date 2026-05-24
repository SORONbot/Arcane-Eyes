import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, UTC
from io import StringIO
from ipaddress import ip_address

from arcane_eyes.core.models import CameraCapability


LEGACY_CAMERA_CACHE_HEADER = ["id", "ip", "display_name"]
CAMERA_CACHE_HEADER = [
    "id",
    "ip",
    "display_name",
    "username",
    "password",
    "capability_json",
    "selected_preview_profile",
    "selected_detail_profile",
    "cache_version",
    "updated_at",
]
CACHE_VERSION = "2"


@dataclass
class CameraCacheEntry:
    id: int
    ip: str
    display_name: str
    username: str = ""
    password: str = ""
    capability: CameraCapability = field(default_factory=CameraCapability)
    selected_preview_profile: str = ""
    selected_detail_profile: str = ""
    cache_version: str = CACHE_VERSION
    updated_at: str = ""


def _valid_identity(row: dict, seen_ids: set[int], seen_ips: set[str]) -> tuple[int, str, str] | None:
    try:
        camera_id = int((row.get("id") or "").strip())
    except ValueError:
        return None
    if camera_id <= 0 or camera_id in seen_ids:
        return None

    ip = (row.get("ip") or "").strip()
    try:
        ip_address(ip)
    except ValueError:
        return None
    if ip in seen_ips:
        return None

    display_name = (row.get("display_name") or "").strip()
    if not display_name:
        return None

    return camera_id, ip, display_name


def parse_camera_cache(serialized_cache: str) -> list[CameraCacheEntry]:
    if not serialized_cache.strip():
        return []

    try:
        reader = csv.DictReader(StringIO(serialized_cache))
        if reader.fieldnames == LEGACY_CAMERA_CACHE_HEADER:
            return _parse_legacy_rows(reader)
        if reader.fieldnames == CAMERA_CACHE_HEADER:
            return _parse_current_rows(reader)
    except csv.Error:
        return []

    return []


def _parse_legacy_rows(reader: csv.DictReader) -> list[CameraCacheEntry]:
    entries = []
    seen_ids: set[int] = set()
    seen_ips: set[str] = set()
    for row in reader:
        if set(row.keys()) != set(LEGACY_CAMERA_CACHE_HEADER):
            return []
        identity = _valid_identity(row, seen_ids, seen_ips)
        if not identity:
            return []
        camera_id, ip, display_name = identity
        entries.append(CameraCacheEntry(id=camera_id, ip=ip, display_name=display_name))
        seen_ids.add(camera_id)
        seen_ips.add(ip)
    return sorted(entries, key=lambda entry: entry.id)


def _parse_current_rows(reader: csv.DictReader) -> list[CameraCacheEntry]:
    entries = []
    seen_ids: set[int] = set()
    seen_ips: set[str] = set()
    for row in reader:
        if set(row.keys()) != set(CAMERA_CACHE_HEADER):
            return []
        identity = _valid_identity(row, seen_ids, seen_ips)
        if not identity:
            return []
        camera_id, ip, display_name = identity

        capability = CameraCapability()
        raw_capability = (row.get("capability_json") or "").strip()
        if raw_capability:
            try:
                capability = CameraCapability.from_dict(json.loads(raw_capability))
            except (json.JSONDecodeError, TypeError):
                capability.stale = True
                capability.warnings.append("Cached capability metadata was malformed and will be re-probed.")

        entries.append(CameraCacheEntry(
            id=camera_id,
            ip=ip,
            display_name=display_name,
            username=(row.get("username") or "").strip(),
            password=row.get("password") or "",
            capability=capability,
            selected_preview_profile=(row.get("selected_preview_profile") or "").strip(),
            selected_detail_profile=(row.get("selected_detail_profile") or "").strip(),
            cache_version=(row.get("cache_version") or CACHE_VERSION).strip(),
            updated_at=(row.get("updated_at") or "").strip(),
        ))
        seen_ids.add(camera_id)
        seen_ips.add(ip)
    return sorted(entries, key=lambda entry: entry.id)


def serialize_camera_cache(entries: list[CameraCacheEntry]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CAMERA_CACHE_HEADER, lineterminator="\n")
    writer.writeheader()
    now = datetime.now(UTC).isoformat()
    for entry in sorted(entries, key=lambda camera: camera.id):
        updated_at = entry.updated_at or now
        writer.writerow({
            "id": entry.id,
            "ip": entry.ip,
            "display_name": entry.display_name,
            "username": entry.username,
            "password": entry.password,
            "capability_json": json.dumps(entry.capability.to_dict(), separators=(",", ":"), sort_keys=True),
            "selected_preview_profile": entry.selected_preview_profile,
            "selected_detail_profile": entry.selected_detail_profile,
            "cache_version": CACHE_VERSION,
            "updated_at": updated_at,
        })
    return output.getvalue()
