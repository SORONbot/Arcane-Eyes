from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from arcane_eyes.core.models import CameraCapability
from arcane_eyes.services.cache_service import CameraCacheEntry
from arcane_eyes.services.credentials_store import CameraCredentials, CredentialsStore


SCHEMA_VERSION = 1


class AppStore:
    def __init__(
        self,
        db_path: Path,
        credentials_store: CredentialsStore | None = None,
    ):
        self.db_path = Path(db_path)
        self.credentials_store = credentials_store
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.create_schema()

    def create_schema(self) -> None:
        self.connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cameras (
                id INTEGER PRIMARY KEY,
                ip TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                vendor TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                setup_method TEXT NOT NULL DEFAULT '',
                mac_address TEXT NOT NULL DEFAULT '',
                hardware_version TEXT NOT NULL DEFAULT '',
                device_identifier TEXT NOT NULL DEFAULT '',
                capability_json TEXT NOT NULL DEFAULT '',
                selected_preview_profile TEXT NOT NULL DEFAULT '',
                selected_detail_profile TEXT NOT NULL DEFAULT '',
                cache_version TEXT NOT NULL DEFAULT '2',
                updated_at TEXT NOT NULL DEFAULT '',
                credentials_missing INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS network_profiles (
                network_range TEXT PRIMARY KEY,
                ssid TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                credentials_missing INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        self.connection.execute(
            "INSERT OR REPLACE INTO app_metadata(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self._ensure_camera_metadata_columns()
        self.connection.commit()

    def _ensure_camera_metadata_columns(self) -> None:
        existing = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(cameras)").fetchall()
        }
        metadata_columns = {
            "vendor": "TEXT NOT NULL DEFAULT ''",
            "model": "TEXT NOT NULL DEFAULT ''",
            "setup_method": "TEXT NOT NULL DEFAULT ''",
            "mac_address": "TEXT NOT NULL DEFAULT ''",
            "hardware_version": "TEXT NOT NULL DEFAULT ''",
            "device_identifier": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in metadata_columns.items():
            if column not in existing:
                self.connection.execute(f"ALTER TABLE cameras ADD COLUMN {column} {definition}")

    def camera_repository(self) -> "CameraRepository":
        return CameraRepository(self.connection, self.credentials_store)

    def network_profile_repository(self) -> "NetworkProfileRepository":
        return NetworkProfileRepository(self.connection)

    def close(self) -> None:
        self.connection.close()


class CameraRepository:
    def __init__(self, connection: sqlite3.Connection, credentials_store: CredentialsStore | None = None):
        self.connection = connection
        self.credentials_store = credentials_store

    def list(self) -> list[CameraCacheEntry]:
        rows = self.connection.execute("SELECT * FROM cameras ORDER BY id").fetchall()
        return [self._row_to_entry(row) for row in rows]

    def add_or_update(self, entry: CameraCacheEntry, credentials_missing: bool = False) -> None:
        self.connection.execute(
            """
            INSERT INTO cameras (
                id, ip, display_name, username, vendor, model, setup_method,
                mac_address, hardware_version, device_identifier, capability_json,
                selected_preview_profile, selected_detail_profile,
                cache_version, updated_at, credentials_missing
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ip) DO UPDATE SET
                id = excluded.id,
                display_name = excluded.display_name,
                username = excluded.username,
                vendor = excluded.vendor,
                model = excluded.model,
                setup_method = excluded.setup_method,
                mac_address = excluded.mac_address,
                hardware_version = excluded.hardware_version,
                device_identifier = excluded.device_identifier,
                capability_json = excluded.capability_json,
                selected_preview_profile = excluded.selected_preview_profile,
                selected_detail_profile = excluded.selected_detail_profile,
                cache_version = excluded.cache_version,
                updated_at = excluded.updated_at,
                credentials_missing = excluded.credentials_missing
            """,
            (
                entry.id,
                entry.ip,
                entry.display_name,
                entry.username,
                entry.vendor,
                entry.model,
                entry.setup_method,
                entry.mac_address,
                entry.hardware_version,
                entry.device_identifier,
                json.dumps(entry.capability.to_dict(), separators=(",", ":"), sort_keys=True),
                entry.selected_preview_profile,
                entry.selected_detail_profile,
                entry.cache_version,
                entry.updated_at,
                1 if credentials_missing else 0,
            ),
        )
        if self.credentials_store and self.credentials_store.is_available:
            self.credentials_store.set_camera_credentials(
                str(entry.id),
                CameraCredentials(username=entry.username, password=entry.password),
            )
        self.connection.commit()

    def replace_all(self, entries: list[CameraCacheEntry]) -> None:
        self.connection.execute("DELETE FROM cameras")
        for entry in entries:
            self.add_or_update(entry)
        self.connection.commit()

    def reorder(self, entries: list[CameraCacheEntry]) -> None:
        for entry in entries:
            self.connection.execute("UPDATE cameras SET id = ? WHERE ip = ?", (entry.id, entry.ip))
        self.connection.commit()

    def delete(self, ip: str) -> None:
        row = self.connection.execute("SELECT id FROM cameras WHERE ip = ?", (ip,)).fetchone()
        self.connection.execute("DELETE FROM cameras WHERE ip = ?", (ip,))
        self.connection.commit()
        if row and self.credentials_store:
            self.credentials_store.delete_camera_credentials(str(row["id"]))

    def save_selected_profiles(self, ip: str, preview_token: str = "", detail_token: str = "") -> None:
        self.connection.execute(
            """
            UPDATE cameras
            SET selected_preview_profile = COALESCE(NULLIF(?, ''), selected_preview_profile),
                selected_detail_profile = COALESCE(NULLIF(?, ''), selected_detail_profile)
            WHERE ip = ?
            """,
            (preview_token, detail_token, ip),
        )
        self.connection.commit()

    def save_capability(self, ip: str, capability: CameraCapability) -> None:
        self.connection.execute(
            "UPDATE cameras SET capability_json = ? WHERE ip = ?",
            (json.dumps(capability.to_dict(), separators=(",", ":"), sort_keys=True), ip),
        )
        self.connection.commit()

    def _row_to_entry(self, row: sqlite3.Row) -> CameraCacheEntry:
        capability = CameraCapability()
        raw_capability = row["capability_json"] or ""
        if raw_capability:
            try:
                capability = CameraCapability.from_dict(json.loads(raw_capability))
            except (json.JSONDecodeError, TypeError):
                capability.stale = True
                capability.warnings.append("Cached capability metadata was malformed and will be re-probed.")
        username = row["username"] or ""
        password = ""
        if self.credentials_store:
            credentials = self.credentials_store.get_camera_credentials(str(row["id"]))
            if credentials:
                username = credentials.username or username
                password = credentials.password
        return CameraCacheEntry(
            id=row["id"],
            ip=row["ip"],
            display_name=row["display_name"],
            username=username,
            password=password,
            vendor=row["vendor"] or "",
            model=row["model"] or "",
            setup_method=row["setup_method"] or "",
            mac_address=row["mac_address"] or "",
            hardware_version=row["hardware_version"] or "",
            device_identifier=row["device_identifier"] or "",
            capability=capability,
            selected_preview_profile=row["selected_preview_profile"] or "",
            selected_detail_profile=row["selected_detail_profile"] or "",
            cache_version=row["cache_version"] or "2",
            updated_at=row["updated_at"] or "",
        )


class NetworkProfileRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def list(self) -> list[dict]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM network_profiles ORDER BY network_range")]

    def delete(self, network_range: str) -> None:
        self.connection.execute("DELETE FROM network_profiles WHERE network_range = ?", (network_range,))
        self.connection.commit()

    def update(self, network_range: str, ssid: str, credentials_missing: bool = False) -> None:
        self.connection.execute(
            """
            INSERT INTO network_profiles(network_range, ssid, credentials_missing)
            VALUES (?, ?, ?)
            ON CONFLICT(network_range) DO UPDATE SET
                ssid = excluded.ssid,
                credentials_missing = excluded.credentials_missing
            """,
            (network_range, ssid, 1 if credentials_missing else 0),
        )
        self.connection.commit()
