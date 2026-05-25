from arcane_eyes.core.models import CameraCapability, StreamProfile, TrackInfo
from arcane_eyes.services.cache_service import CameraCacheEntry
from arcane_eyes.services.credentials_store import CameraCredentials, DisabledCredentialsStore
from arcane_eyes.services.storage_service import AppStore


class FakeCredentialsStore(DisabledCredentialsStore):
    def __init__(self, available=True):
        self.available = available
        self.camera_credentials = {}

    @property
    def is_available(self) -> bool:
        return self.available

    def get_camera_credentials(self, camera_id: str) -> CameraCredentials | None:
        return self.camera_credentials.get(camera_id)

    def set_camera_credentials(self, camera_id: str, credentials: CameraCredentials) -> bool:
        if not self.available:
            return False
        self.camera_credentials[camera_id] = credentials
        return True

    def delete_camera_credentials(self, camera_id: str) -> None:
        self.camera_credentials.pop(camera_id, None)


def test_app_store_creates_empty_schema(tmp_path):
    app_store = AppStore(tmp_path / "arcane.sqlite3", credentials_store=FakeCredentialsStore())

    assert app_store.camera_repository().list() == []
    schema_version = app_store.connection.execute(
        "SELECT value FROM app_metadata WHERE key = 'schema_version'"
    ).fetchone()
    assert schema_version["value"] == "1"


def test_camera_repository_stores_password_in_credentials_store_only(tmp_path):
    credentials_store = FakeCredentialsStore()
    app_store = AppStore(tmp_path / "arcane.sqlite3", credentials_store=credentials_store)
    repository = app_store.camera_repository()

    repository.add_or_update(
        CameraCacheEntry(
            id=1,
            ip="192.168.100.20",
            display_name="Front Door",
            username="admin",
            password="secret",
        )
    )

    row = app_store.connection.execute("SELECT * FROM cameras WHERE id = 1").fetchone()
    assert "password" not in row.keys()
    assert credentials_store.camera_credentials["1"] == CameraCredentials("admin", "secret")
    assert repository.list()[0].password == "secret"


def test_camera_repository_persists_order_profiles_and_capability_json(tmp_path):
    app_store = AppStore(tmp_path / "arcane.sqlite3", credentials_store=FakeCredentialsStore())
    repository = app_store.camera_repository()
    capability = CameraCapability(
        profiles=[
            StreamProfile(
                token="main",
                name="Main",
                uri="rtsp://192.168.100.20/main",
                valid=True,
                video=TrackInfo(kind="video", codec="h264", width=1920, height=1080),
            )
        ],
        stale=False,
    )

    repository.add_or_update(CameraCacheEntry(id=2, ip="192.168.100.21", display_name="Second"))
    repository.add_or_update(
        CameraCacheEntry(
            id=1,
            ip="192.168.100.20",
            display_name="First",
            capability=capability,
            selected_detail_profile="main",
        )
    )

    entries = repository.list()
    assert [entry.ip for entry in entries] == ["192.168.100.20", "192.168.100.21"]
    assert entries[0].selected_detail_profile == "main"
    assert entries[0].capability.valid_profiles()[0].video.codec == "h264"
