import json
import random
import string
import time
from dataclasses import dataclass, field
from ipaddress import ip_network
from pathlib import Path
from typing import Callable, Iterable, Set

from cryptography.fernet import Fernet, InvalidToken

from arcane_eyes.core.config import (
    DEFAULT_SCAN_RANGE,
    SETUP_QR_CREDENTIAL_CACHE_PATH,
    SETUP_QR_FERNET_KEY,
)
from arcane_eyes.services.discovery_service import NetworkDiscoveryService


def create_bind_token() -> str:
    suffix = "".join(random.choices(string.ascii_letters + string.digits, k=5))
    return f"and_{suffix}"


def normalize_network_range(network_range: str) -> str:
    value = network_range.strip()
    if not value:
        raise ValueError("Enter a network range to scan.")
    try:
        return str(ip_network(value, strict=False))
    except ValueError as exc:
        raise ValueError("Enter a valid CIDR network range, for example 192.168.100.0/24.") from exc


@dataclass(frozen=True)
class WifiCredentials:
    ssid: str
    password: str = ""


@dataclass(frozen=True)
class WifiProvisioningPayload:
    ssid: str
    password: str = ""
    network_range: str = DEFAULT_SCAN_RANGE
    user_id: str = "-1"
    bind_token: str = field(default_factory=create_bind_token)

    @property
    def encoded_password(self) -> str:
        if not self.password or not self.password.strip():
            return "null"
        return self.password

    def to_qr_text(self) -> str:
        return "\n".join([
            self.bind_token,
            self.ssid,
            self.encoded_password,
            self.user_id,
        ])


class SetupQrCredentialCache:
    missing_key_warning = (
        "Setup QR credential caching is disabled. Set SETUP_QR_FERNET_KEY "
        "to enable encrypted SSID/password storage."
    )

    def __init__(
        self,
        fernet_key: str | None = SETUP_QR_FERNET_KEY,
        cache_path: Path | str = SETUP_QR_CREDENTIAL_CACHE_PATH,
    ):
        self.cache_path = Path(cache_path)
        self.warning: str | None = None
        self._fernet: Fernet | None = None

        if not fernet_key:
            self.warning = self.missing_key_warning
            return

        try:
            self._fernet = Fernet(fernet_key.encode() if isinstance(fernet_key, str) else fernet_key)
        except (TypeError, ValueError):
            self.warning = "Setup QR credential caching is disabled because SETUP_QR_FERNET_KEY is invalid."

    @property
    def is_enabled(self) -> bool:
        return self._fernet is not None

    def load(self, network_range: str) -> WifiCredentials | None:
        if not self.is_enabled:
            return None

        profiles = self._read_profiles()
        profile = profiles.get(normalize_network_range(network_range))
        if not isinstance(profile, dict):
            return None

        ssid = profile.get("ssid")
        password = profile.get("password", "")
        if not isinstance(ssid, str) or not isinstance(password, str):
            return None
        return WifiCredentials(ssid=ssid, password=password)

    def save(self, network_range: str, ssid: str, password: str) -> bool:
        if not self.is_enabled:
            return False

        normalized_range = normalize_network_range(network_range)
        profiles = self._read_profiles()
        profiles[normalized_range] = {"ssid": ssid, "password": password}
        self._write_profiles(profiles)
        return True

    def list_profiles(self) -> dict[str, WifiCredentials]:
        if not self.is_enabled:
            return {}

        profiles = self._read_profiles()
        credentials = {}
        for network_range, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            ssid = profile.get("ssid")
            password = profile.get("password", "")
            if isinstance(ssid, str) and isinstance(password, str):
                credentials[network_range] = WifiCredentials(ssid=ssid, password=password)
        return credentials

    def update_profile(self, old_range: str, new_range: str, ssid: str, password: str) -> bool:
        if not self.is_enabled:
            return False

        old_normalized_range = normalize_network_range(old_range)
        new_normalized_range = normalize_network_range(new_range)
        profiles = self._read_profiles()
        if old_normalized_range != new_normalized_range:
            profiles.pop(old_normalized_range, None)
        profiles[new_normalized_range] = {"ssid": ssid, "password": password}
        self._write_profiles(profiles)
        return True

    def _read_profiles(self) -> dict[str, dict[str, str]]:
        if not self.cache_path.exists():
            return {}

        assert self._fernet is not None
        try:
            encrypted = self.cache_path.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            payload = json.loads(decrypted.decode("utf-8"))
        except (OSError, InvalidToken, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Unable to read encrypted setup QR credential cache.") from exc

        if not isinstance(payload, dict):
            return {}
        profiles = payload.get("profiles", {})
        if not isinstance(profiles, dict):
            return {}
        return profiles

    def _write_profiles(self, profiles: dict[str, dict[str, str]]) -> None:
        assert self._fernet is not None
        payload = {"version": 1, "profiles": profiles}
        encrypted = self._fernet.encrypt(json.dumps(payload, sort_keys=True).encode("utf-8"))
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_bytes(encrypted)
        try:
            self.cache_path.chmod(0o600)
        except OSError:
            pass


class CameraAdoptionService:
    def __init__(
        self,
        discovery_service: NetworkDiscoveryService,
        network_range: str = DEFAULT_SCAN_RANGE,
        poll_interval_seconds: float = 3.0,
    ):
        self.discovery_service = discovery_service
        self.network_range = normalize_network_range(network_range)
        self.poll_interval_seconds = poll_interval_seconds

    def wait_for_new_camera(
        self,
        known_ips: Iterable[str],
        timeout_seconds: float,
        should_stop: Callable[[], bool] | None = None,
        on_progress: Callable[[int], None] | None = None,
        network_range: str | None = None,
    ) -> str | None:
        known_ip_set: Set[str] = set(known_ips)
        scan_range = normalize_network_range(network_range or self.network_range)
        start_time = time.monotonic()
        should_stop = should_stop or (lambda: False)

        while not should_stop():
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout_seconds:
                return None

            remaining_seconds = max(0, int(timeout_seconds - elapsed))
            if on_progress:
                on_progress(remaining_seconds)

            discovered_ips = self.discovery_service.scan(scan_range)
            for ip in discovered_ips:
                if ip not in known_ip_set:
                    return ip

            sleep_until = time.monotonic() + self.poll_interval_seconds
            while time.monotonic() < sleep_until:
                if should_stop():
                    return None
                if time.monotonic() - start_time >= timeout_seconds:
                    return None
                time.sleep(0.1)

        return None
