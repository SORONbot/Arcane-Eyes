import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton, QTabWidget

import arcane_eyes.main as main_module
import arcane_eyes.ui.main_window as main_window_module
from arcane_eyes.main import ArcaneEyesMainWindow, CameraCacheEntry, FeedCard
from arcane_eyes.ui.camera_widget import CameraDisplayWidget


class FakeStreamManager:
    def __init__(self):
        self.started_ips = []
        self.stopped_ips = []

    def start_stream(self, device, stream_service, recorder_service, on_frame_callback, stream_key=None, stream_url=None):
        self.started_ips.append(stream_key or device.ip)

    def stop_stream(self, ip):
        self.stopped_ips.append(ip)

    def stop_all(self):
        pass


class FakeDiscoveryService:
    started_scans = []

    def __init__(self, timeout):
        self.timeout = timeout

    def start_async_scan(self, network_range, on_found):
        self.started_scans.append(network_range)


class FakeCapabilityEnrichmentService:
    def enrich(self, ip, username="", password="", port=554):
        from arcane_eyes.core.models import CameraCapability

        return CameraCapability(stale=False)


class FakeCameraRepository:
    def __init__(self, entries):
        self.entries = {entry.ip: entry for entry in entries}

    def list(self):
        return sorted(self.entries.values(), key=lambda entry: entry.id)

    def replace_all(self, entries):
        self.entries = {entry.ip: entry for entry in entries}


class FakeNetworkProfileRepository:
    def __init__(self):
        self.rows = []

    def list(self):
        return list(self.rows)

    def update(self, network_range, ssid, credentials_missing=False):
        self.rows = [row for row in self.rows if row["network_range"] != network_range]
        self.rows.append(
            {
                "network_range": network_range,
                "ssid": ssid,
                "credentials_missing": 1 if credentials_missing else 0,
            }
        )


class FakeCredentialsStore:
    is_available = True

    def __init__(self):
        self.wifi_credentials = {}

    def get_camera_credentials(self, camera_id):
        return None

    def set_camera_credentials(self, camera_id, credentials):
        return True

    def delete_camera_credentials(self, camera_id):
        return None

    def get_wifi_credentials(self, profile_id):
        return self.wifi_credentials.get(profile_id)

    def set_wifi_credentials(self, profile_id, credentials):
        self.wifi_credentials[profile_id] = credentials
        return True

    def delete_wifi_credentials(self, profile_id):
        self.wifi_credentials.pop(profile_id, None)


class FakeAppStore:
    entries = []

    def __init__(self, db_path, credentials_store=None):
        self.camera_repo = FakeCameraRepository(self.entries)
        self.network_repo = FakeNetworkProfileRepository()

    def camera_repository(self):
        return self.camera_repo

    def network_profile_repository(self):
        return self.network_repo


def install_dashboard_fakes(monkeypatch, tmp_path, entries=None):
    FakeAppStore.entries = entries or []

    FakeDiscoveryService.started_scans = []
    monkeypatch.setattr(main_module, "DATABASE_PATH", tmp_path / "arcane.sqlite3")
    monkeypatch.setattr(main_module, "AppStore", FakeAppStore)
    monkeypatch.setattr(main_module, "StreamManager", FakeStreamManager)
    monkeypatch.setattr(main_module, "NetworkDiscoveryService", FakeDiscoveryService)
    monkeypatch.setattr(main_module, "CameraCapabilityEnrichmentService", FakeCapabilityEnrichmentService)
    monkeypatch.setattr(main_window_module, "DEFAULT_SCAN_RANGE", "192.168.1.0/24")
    monkeypatch.setattr(main_window_module, "KeyringCredentialsStore", FakeCredentialsStore)
    monkeypatch.setattr(CameraDisplayWidget, "_init_ptz", lambda self: None)


def find_label_text(window, text):
    return any(label.text() == text for label in window.findChildren(QLabel))


def test_no_cache_startup_shows_empty_dashboard_without_scanning(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path)

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)

    assert find_label_text(window, "No eyes found yet")
    assert FakeDiscoveryService.started_scans == []
    assert window.prev_page_button.isEnabled() is False
    assert window.next_page_button.isEnabled() is False


def test_scan_keeps_button_label_and_updates_empty_message(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path)

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "get_configured_scan_range", lambda: "192.168.1.0/24")

    window.run_background_scan()

    assert window.scan_button.isEnabled() is False
    assert window.scan_button.text() == "Scan Network"
    assert find_label_text(window, "Scanning the Network")

    window.on_scan_finished()

    assert window.scan_button.isEnabled() is True
    assert find_label_text(window, "No eyes found yet")


def test_scan_without_network_opens_network_settings_add_row(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path)

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)

    window.run_background_scan()

    tabs = window.findChild(QTabWidget)
    assert tabs is not None
    assert tabs.currentIndex() == 1
    assert tabs.tabText(1) == "Networks"
    assert any(button.text() == "Add Network" for button in window.findChildren(QPushButton))
    assert any(line_edit.text() == "192.168.1.0/24" for line_edit in window.findChildren(QLineEdit))
    assert FakeDiscoveryService.started_scans == []


def test_saving_network_profile_enables_scan(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path)

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)

    window.save_network_profile(
        "",
        QLineEdit("192.168.1.22/24"),
        QLineEdit(""),
        QLineEdit(""),
    )
    window.run_background_scan()

    assert window.network_profile_repository.list()[0]["network_range"] == "192.168.1.0/24"
    qtbot.waitUntil(lambda: FakeDiscoveryService.started_scans == ["192.168.1.0/24"])


def test_saved_network_rows_include_generate_qr_button(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path)

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)
    window.save_network_profile(
        "",
        QLineEdit("192.168.1.0/24"),
        QLineEdit("LabNet"),
        QLineEdit("secret"),
    )

    assert any(button.text() == "Generate QR" for button in window.findChildren(QPushButton))


def test_cached_startup_restores_sorted_feeds_directly(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(
        monkeypatch,
        tmp_path,
        [
            CameraCacheEntry(id=2, ip="192.168.100.2", display_name="Second"),
            CameraCacheEntry(id=1, ip="192.168.100.10", display_name="First"),
            CameraCacheEntry(id=3, ip="10.0.0.1", display_name="Third"),
        ],
    )

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)

    assert window.sorted_camera_ips() == ["192.168.100.10", "192.168.100.2", "10.0.0.1"]
    assert window.stream_manager.started_ips == [
        "192.168.100.10:preview",
        "192.168.100.2:preview",
        "10.0.0.1:preview",
    ]
    assert FakeDiscoveryService.started_scans == []


def test_clicking_feed_opens_detail_screen(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path, [CameraCacheEntry(id=1, ip="192.168.100.20", display_name="Front Door")])

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)

    card = window.findChild(FeedCard)
    qtbot.mouseClick(card, Qt.MouseButton.LeftButton)

    assert find_label_text(window, "Camera Detail - Front Door")
    assert any(button.text() == "Record" for button in window.findChildren(QPushButton))
    assert any(button.text() == "Reload Stream" for button in window.findChildren(QPushButton))


def test_feed_cards_expose_reload_control(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path, [CameraCacheEntry(id=1, ip="192.168.100.20", display_name="Front Door")])

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)

    assert any(button.objectName() == "reloadStreamButton" for button in window.findChildren(QPushButton))


def test_settings_button_opens_settings_tabs(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path, [CameraCacheEntry(id=1, ip="192.168.100.20", display_name="Front Door")])

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.settings_button, Qt.MouseButton.LeftButton)

    tabs = window.findChild(QTabWidget)
    assert tabs is not None
    assert tabs.tabText(0) == "Configured Cameras"
    assert tabs.tabText(1) == "Networks"
    assert find_label_text(window, "1")
    assert any(line_edit.text() == "192.168.100.20" for line_edit in window.findChildren(QLineEdit))
    assert any(line_edit.text() == "Front Door" for line_edit in window.findChildren(QLineEdit))


def test_editing_display_name_updates_repository_and_feed_label(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path, [CameraCacheEntry(id=1, ip="192.168.100.20", display_name="Front Door")])

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)
    window.save_camera_settings(
        "192.168.100.20",
        QLineEdit("192.168.100.20"),
        QLineEdit("Porch"),
        QLineEdit(""),
        QLineEdit(""),
    )
    window.show_feed_dashboard()

    assert window.camera_repository.list()[0].display_name == "Porch"
    assert find_label_text(window, "Porch")


def test_editing_ip_restarts_stream_for_new_ip(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path, [CameraCacheEntry(id=1, ip="192.168.100.20", display_name="Front Door")])

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)
    window.save_camera_settings(
        "192.168.100.20",
        QLineEdit("192.168.100.21"),
        QLineEdit("Front Door"),
        QLineEdit(""),
        QLineEdit(""),
    )

    assert window.stream_manager.stopped_ips == ["192.168.100.20:preview", "192.168.100.20:detail"]
    assert window.sorted_camera_ips() == ["192.168.100.21"]


def test_reorder_swaps_ids_and_dashboard_order(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(
        monkeypatch,
        tmp_path,
        [
            CameraCacheEntry(id=1, ip="192.168.100.20", display_name="First"),
            CameraCacheEntry(id=2, ip="192.168.100.21", display_name="Second"),
        ],
    )

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)
    window.move_camera_entry("192.168.100.21", -1)

    assert window.sorted_camera_entries() == [
        CameraCacheEntry(id=1, ip="192.168.100.21", display_name="Second"),
        CameraCacheEntry(id=2, ip="192.168.100.20", display_name="First"),
    ]


def test_newly_discovered_camera_gets_next_cache_id(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path, [CameraCacheEntry(id=5, ip="192.168.100.20", display_name="Front Door")])

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)
    window.add_camera("192.168.100.30")

    assert window.camera_entries["192.168.100.30"].id == 6


def test_network_settings_shows_add_network_action(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path)

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)
    window.show_network_settings()

    assert find_label_text(window, "No saved networks. Add a network before scanning.")
    assert any(button.text() == "Add Network" for button in window.findChildren(QPushButton))


def test_generate_network_qr_opens_modal_dialog(qtbot, monkeypatch, tmp_path):
    install_dashboard_fakes(monkeypatch, tmp_path)
    shown = {}

    window = ArcaneEyesMainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(
        window,
        "show_network_qr_dialog",
        lambda network_range, pixmap: shown.update({"network_range": network_range, "pixmap": pixmap}),
    )

    window.generate_network_qr(
        QLineEdit("192.168.1.0/24"),
        QLineEdit("LabNet"),
        QLineEdit("secret"),
    )

    assert shown["network_range"] == "192.168.1.0/24"
    assert shown["pixmap"] is not None
