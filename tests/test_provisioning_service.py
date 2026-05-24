from cryptography.fernet import Fernet

from arcane_eyes.logic.adoption_worker import CameraAdoptionWorker
from arcane_eyes.services.provisioning_service import (
    CameraAdoptionService,
    SetupQrCredentialCache,
    WifiProvisioningPayload,
    create_bind_token,
    normalize_network_range,
)


class FakeDiscoveryService:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.last_network_range = None

    def scan(self, network_range):
        self.calls += 1
        self.last_network_range = network_range
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return []


def test_wifi_payload_formats_qr_text_with_password():
    payload = WifiProvisioningPayload(
        ssid="LabNet",
        password="secret",
        bind_token="and_abc12",
    )

    assert payload.to_qr_text() == "and_abc12\nLabNet\nsecret\n-1"


def test_wifi_payload_encodes_empty_password_as_null():
    payload = WifiProvisioningPayload(
        ssid="OpenNet",
        password=" ",
        bind_token="and_abc12",
    )

    assert payload.to_qr_text() == "and_abc12\nOpenNet\nnull\n-1"


def test_bind_token_format():
    token = create_bind_token()

    assert token.startswith("and_")
    assert len(token) == 9


def test_adoption_ignores_known_ips_and_returns_new_camera():
    discovery = FakeDiscoveryService([
        ["192.168.100.10"],
        ["192.168.100.10", "192.168.100.33"],
    ])
    service = CameraAdoptionService(
        discovery,
        network_range="192.168.100.0/24",
        poll_interval_seconds=0,
    )

    assert service.wait_for_new_camera(["192.168.100.10"], timeout_seconds=1) == "192.168.100.33"


def test_adoption_times_out_cleanly():
    discovery = FakeDiscoveryService([[], []])
    service = CameraAdoptionService(
        discovery,
        network_range="192.168.100.0/24",
        poll_interval_seconds=0,
    )

    assert service.wait_for_new_camera([], timeout_seconds=0.01) is None


def test_adoption_propagates_discovery_errors():
    discovery = FakeDiscoveryService([RuntimeError("scan failed")])
    service = CameraAdoptionService(discovery, poll_interval_seconds=0)

    try:
        service.wait_for_new_camera([], timeout_seconds=1)
    except RuntimeError as exc:
        assert str(exc) == "scan failed"
    else:
        raise AssertionError("Expected discovery error to propagate")


def test_credential_cache_encrypts_saved_credentials(tmp_path):
    key = Fernet.generate_key().decode()
    cache_path = tmp_path / "setup_credentials.cache"
    cache = SetupQrCredentialCache(fernet_key=key, cache_path=cache_path)

    assert cache.save("192.168.100.0/24", "LabNet", "secret") is True

    raw_cache = cache_path.read_bytes()
    assert b"LabNet" not in raw_cache
    assert b"secret" not in raw_cache
    assert b"192.168.100.0" not in raw_cache

    loaded = cache.load("192.168.100.0/24")
    assert loaded.ssid == "LabNet"
    assert loaded.password == "secret"


def test_credential_cache_keeps_profiles_by_network_range(tmp_path):
    key = Fernet.generate_key().decode()
    cache = SetupQrCredentialCache(fernet_key=key, cache_path=tmp_path / "setup_credentials.cache")

    cache.save("192.168.100.0/24", "LabNet", "secret")
    cache.save("10.0.0.0/24", "OfficeNet", "other-secret")

    lab = cache.load("192.168.100.15/24")
    office = cache.load("10.0.0.8/24")

    assert lab.ssid == "LabNet"
    assert lab.password == "secret"
    assert office.ssid == "OfficeNet"
    assert office.password == "other-secret"


def test_credential_cache_lists_profiles(tmp_path):
    key = Fernet.generate_key().decode()
    cache = SetupQrCredentialCache(fernet_key=key, cache_path=tmp_path / "setup_credentials.cache")

    cache.save("192.168.100.0/24", "LabNet", "secret")
    cache.save("10.0.0.0/24", "OfficeNet", "other-secret")

    profiles = cache.list_profiles()

    assert profiles["192.168.100.0/24"].ssid == "LabNet"
    assert profiles["192.168.100.0/24"].password == "secret"
    assert profiles["10.0.0.0/24"].ssid == "OfficeNet"
    assert profiles["10.0.0.0/24"].password == "other-secret"


def test_credential_cache_updates_profile(tmp_path):
    key = Fernet.generate_key().decode()
    cache = SetupQrCredentialCache(fernet_key=key, cache_path=tmp_path / "setup_credentials.cache")

    cache.save("192.168.100.0/24", "LabNet", "secret")

    assert cache.update_profile("192.168.100.0/24", "10.0.0.0/24", "OfficeNet", "other-secret") is True
    assert cache.load("192.168.100.0/24") is None
    updated = cache.load("10.0.0.0/24")
    assert updated.ssid == "OfficeNet"
    assert updated.password == "other-secret"


def test_credential_cache_is_disabled_without_key(tmp_path):
    cache_path = tmp_path / "setup_credentials.cache"
    cache = SetupQrCredentialCache(fernet_key="", cache_path=cache_path)

    assert cache.is_enabled is False
    assert "disabled" in cache.warning
    assert cache.save("192.168.100.0/24", "LabNet", "secret") is False
    assert cache.update_profile("192.168.100.0/24", "10.0.0.0/24", "LabNet", "secret") is False
    assert cache.list_profiles() == {}
    assert cache.load("192.168.100.0/24") is None
    assert not cache_path.exists()


def test_network_range_validation_normalizes_cidr():
    assert normalize_network_range(" 192.168.100.22/24 ") == "192.168.100.0/24"


def test_network_range_validation_rejects_invalid_values():
    try:
        normalize_network_range("not-a-network")
    except ValueError as exc:
        assert "valid CIDR" in str(exc)
    else:
        raise AssertionError("Expected invalid network range to fail validation")


def test_adoption_service_uses_per_flow_network_range_override():
    discovery = FakeDiscoveryService([["10.0.0.22"]])
    service = CameraAdoptionService(
        discovery,
        network_range="192.168.100.0/24",
        poll_interval_seconds=0,
    )

    assert service.wait_for_new_camera(
        [],
        timeout_seconds=1,
        network_range="10.0.0.0/24",
    ) == "10.0.0.22"

    assert discovery.last_network_range == "10.0.0.0/24"


class FakeAdoptionService:
    def __init__(self):
        self.received_network_range = None

    def wait_for_new_camera(self, known_ips, timeout_seconds, should_stop=None, network_range=None):
        self.received_network_range = network_range
        return None


def test_adoption_worker_passes_network_range_override():
    service = FakeAdoptionService()
    worker = CameraAdoptionWorker(
        adoption_service=service,
        known_ips=[],
        timeout_seconds=0.01,
        network_range="10.0.0.0/24",
    )

    worker.run()

    assert service.received_network_range == "10.0.0.0/24"
