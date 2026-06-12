import sys
from functools import partial
from ipaddress import ip_address
from pathlib import Path

from PyQt6.QtCore import Qt, QThreadPool, pyqtSlot, QRunnable, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QKeyEvent, QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QComboBox,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from arcane_eyes.core.config import DEFAULT_SCAN_RANGE, DATABASE_PATH
from arcane_eyes.core.constants import (
    HEIGHT,
    SCAN_TIMEOUT,
    WIDTH,
)
from arcane_eyes.core.models import CameraCapability, CameraDevice, ConnectionStatus
from arcane_eyes.logic.stream_manager import StreamManager
from arcane_eyes.services.cache_service import (
    CameraCacheEntry,
)
from arcane_eyes.services.capability_service import CameraCapabilityEnrichmentService
from arcane_eyes.services.discovery_service import NetworkDiscoveryService
from arcane_eyes.services.ptz_service import OnvifPTZService
from arcane_eyes.services.provisioning_service import (
    GinatexQrProvisioningAdapter,
    normalize_network_range,
)
from arcane_eyes.services.recorder_service import PyAVRecorderService
from arcane_eyes.services.credentials_store import KeyringCredentialsStore, WifiCredentials as StoredWifiCredentials
from arcane_eyes.services.storage_service import AppStore
from arcane_eyes.services.stream_service import StreamService
from arcane_eyes.ui.camera_widget import CameraDisplayWidget
from arcane_eyes.ui.qr import make_qr_pixmap
from arcane_eyes.ui.record_dialog import RecordDialog
from arcane_eyes.ui.style.styles import STYLE_RECORD_BTN_ACTIVE, STYLE_RECORD_BTN_DEFAULT
from arcane_eyes.ui.widgets import FeedCard


APP_ICON_PATH = Path(__file__).resolve().parents[3] / "assets" / "arcane-eye-icon.png"
FEEDS_PER_PAGE = 4
CLOCKWISE_GRID_POSITIONS = [(0, 0), (0, 1), (1, 1), (1, 0)]


def make_app_icon() -> QIcon:
    return QIcon(str(APP_ICON_PATH))


def grid_position_for_feed(slot_index: int) -> tuple[int, int]:
    return CLOCKWISE_GRID_POSITIONS[slot_index]


def _compat_symbol(name: str, default):
    main_module = sys.modules.get("arcane_eyes.main")
    return getattr(main_module, name, default) if main_module else default


def _database_path() -> Path:
    main_module = sys.modules.get("arcane_eyes.main")
    configured_database = getattr(main_module, "DATABASE_PATH", DATABASE_PATH) if main_module else DATABASE_PATH
    return Path(configured_database)


class DiscoveryWorkerSignals(QObject):
    camera_found = pyqtSignal(object)
    finished = pyqtSignal()
    error = pyqtSignal(str)


class DiscoveryWorker(QRunnable):
    def __init__(self, discovery_service: NetworkDiscoveryService, enrichment_service: CameraCapabilityEnrichmentService, network_range: str):
        super().__init__()
        self.service = discovery_service
        self.enrichment_service = enrichment_service
        self.network_range = network_range
        self.signals = DiscoveryWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            def emit_enriched(ip: str):
                capability = self.enrichment_service.enrich(ip)
                self.signals.camera_found.emit((ip, capability))

            self.service.start_async_scan(self.network_range, emit_enriched)
            self.signals.finished.emit()
        except Exception as e:
            self.signals.error.emit(str(e))


class CapabilityRefreshSignals(QObject):
    refreshed = pyqtSignal(object)


class CapabilityRefreshWorker(QRunnable):
    def __init__(self, enrichment_service: CameraCapabilityEnrichmentService, ip: str, username: str = "", password: str = ""):
        super().__init__()
        self.enrichment_service = enrichment_service
        self.ip = ip
        self.username = username
        self.password = password
        self.signals = CapabilityRefreshSignals()

    @pyqtSlot()
    def run(self):
        capability = self.enrichment_service.enrich(self.ip, username=self.username, password=self.password)
        self.signals.refreshed.emit((self.ip, capability))


class ArcaneEyesMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arcane Eyes")
        self.setWindowIcon(make_app_icon())
        self.resize(1280, 720)
        self.setMinimumSize(760, 480)

        self.stream_manager = _compat_symbol("StreamManager", StreamManager)()
        self.stream_service = StreamService(target_width=WIDTH, target_height=HEIGHT)
        self.discovery_service = _compat_symbol("NetworkDiscoveryService", NetworkDiscoveryService)(timeout=SCAN_TIMEOUT)
        self.enrichment_service = _compat_symbol("CameraCapabilityEnrichmentService", CameraCapabilityEnrichmentService)()
        self.credentials_store = KeyringCredentialsStore()
        app_store_cls = _compat_symbol("AppStore", AppStore)
        self.app_store = app_store_cls(db_path=_database_path(), credentials_store=self.credentials_store)
        self.camera_repository = self.app_store.camera_repository()
        self.network_profile_repository = self.app_store.network_profile_repository()
        self.thread_pool = QThreadPool()

        self.active_devices = {}
        self.active_recorders = {}
        self.camera_entries = {}
        self.display_widgets = {}
        self.feed_cards = {}
        self.stream_status_labels = {}
        self.active_record_buttons = {}
        self.ptz_services = {}
        self.current_page = 0
        self.is_scanning_network = False
        self.show_new_network_row = False
        self._shutdown_started = False
        self._skip_close_confirmation = False

        self._setup_ui()
        for camera_entry in self.load_cached_cameras():
            self.add_camera(camera_entry.ip, persist=False, cache_entry=camera_entry)
        self.show_feed_dashboard()

    def _setup_ui(self):
        self.central_widget = QWidget()
        self.root_layout = QHBoxLayout(self.central_widget)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(150)
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setStyleSheet("""
            QFrame#sidebar {
                background: #243344;
                border-right: 1px solid #33475d;
            }
            QPushButton {
                min-height: 38px;
                text-align: left;
                padding-left: 14px;
            }
        """)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 14, 10, 14)
        sidebar_layout.setSpacing(10)

        app_label = QLabel("Arcane Eyes")
        app_label.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #d7e1ea; background: transparent; border: none;"
        )
        sidebar_layout.addWidget(app_label)

        self.feeds_button = QPushButton("Feeds")
        self.feeds_button.clicked.connect(self.show_feed_dashboard)
        sidebar_layout.addWidget(self.feeds_button)

        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.show_settings_screen)
        sidebar_layout.addWidget(self.settings_button)

        self.scan_button = QPushButton("Scan Network")
        self.scan_button.clicked.connect(self.run_background_scan)
        sidebar_layout.addWidget(self.scan_button)

        sidebar_layout.addStretch(1)

        self.quit_button = QPushButton("Quit")
        self.quit_button.clicked.connect(self.close)
        sidebar_layout.addWidget(self.quit_button)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(18, 18, 18, 18)
        self.content_layout.setSpacing(14)

        self.root_layout.addWidget(self.sidebar)
        self.root_layout.addWidget(self.content_widget, 1)
        self.setCentralWidget(self.central_widget)

    def _clear_content(self):
        for widget in self.display_widgets.values():
            widget.stop_motors()
        self.active_record_buttons.clear()
        self.display_widgets.clear()
        self.feed_cards.clear()
        self.stream_status_labels.clear()
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            child_layout = item.layout()
            if child_layout:
                self._clear_layout(child_layout)

    def stream_key(self, ip: str, usage: str) -> str:
        return f"{ip}:{usage}"

    def start_camera_display_stream(self, ip: str, usage: str):
        device = self.active_devices.get(ip)
        recorder = self.active_recorders.get(ip)
        if not device or not recorder:
            return

        stream_key = self.stream_key(ip, usage)
        stream_url = device.preview_stream_url if usage == "preview" else device.detail_stream_url
        kwargs = {
            "device": device,
            "stream_service": self.stream_service,
            "recorder_service": recorder,
            "on_frame_callback": partial(self.on_frame_received, stream_key),
            "stream_key": stream_key,
            "stream_url": stream_url,
            "on_status_callback": self.on_stream_status_changed,
        }
        try:
            self.stream_manager.start_stream(**kwargs)
        except TypeError as exc:
            if "on_status_callback" not in str(exc):
                raise
            kwargs.pop("on_status_callback")
            self.stream_manager.start_stream(**kwargs)

    def refresh_capability_async(self, entry: CameraCacheEntry):
        worker = CapabilityRefreshWorker(
            self.enrichment_service,
            entry.ip,
            username=entry.username,
            password=entry.password,
        )
        worker.signals.refreshed.connect(self.on_capability_refreshed)
        self.thread_pool.start(worker)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            child_layout = item.layout()
            if child_layout:
                self._clear_layout(child_layout)

    def load_cached_cameras(self) -> list[CameraCacheEntry]:
        return self.camera_repository.list()

    def save_cached_cameras(self):
        self.camera_repository.replace_all(self.sorted_camera_entries())

    def _save_cache(self):
        self.save_cached_cameras()

    def load_cached_ips(self) -> list[str]:
        return [entry.ip for entry in self.load_cached_cameras()]

    def save_cached_ips(self):
        self.save_cached_cameras()

    def sorted_camera_entries(self) -> list[CameraCacheEntry]:
        return sorted(self.camera_entries.values(), key=lambda entry: entry.id)

    def sorted_camera_ips(self) -> list[str]:
        return [entry.ip for entry in self.sorted_camera_entries()]

    def next_camera_cache_id(self) -> int:
        if not self.camera_entries:
            return 1
        return max(entry.id for entry in self.camera_entries.values()) + 1

    def display_name_for_ip(self, ip: str) -> str:
        entry = self.camera_entries.get(ip)
        return entry.display_name if entry else ip

    def show_feed_dashboard(self):
        self._clear_content()
        self.refresh_feed_grid()

    def refresh_feed_grid(self):
        ips = self.sorted_camera_ips()
        max_page = max(0, (len(ips) - 1) // FEEDS_PER_PAGE)
        self.current_page = min(self.current_page, max_page)

        title = QLabel("Feeds")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #d7e1ea;")
        self.content_layout.addWidget(title)

        feed_area = QFrame()
        feed_area.setObjectName("feedArea")
        feed_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        feed_area.setStyleSheet("""
            QFrame#feedArea {
                background: #13202c;
                border: 1px solid #26394d;
                border-radius: 8px;
            }
        """)
        feed_layout = QGridLayout(feed_area)
        feed_layout.setContentsMargins(12, 12, 12, 12)
        feed_layout.setSpacing(12)

        if not ips:
            message = "Scanning the Network" if self.is_scanning_network else "No eyes found yet"
            empty_label = QLabel(message)
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("font-size: 26px; color: #aebdcc; font-weight: 700;")
            feed_layout.addWidget(empty_label, 0, 0, 2, 2)
        else:
            page_start = self.current_page * FEEDS_PER_PAGE
            page_ips = ips[page_start:page_start + FEEDS_PER_PAGE]
            for slot_index, ip in enumerate(page_ips):
                display_widget = CameraDisplayWidget(ip=ip, show_ptz=False, fixed_size=False)
                stream_key = self.stream_key(ip, "preview")
                self.display_widgets[stream_key] = display_widget
                self.start_camera_display_stream(ip, "preview")
                card = FeedCard(ip, self.display_name_for_ip(ip), display_widget, self.open_feed_detail, self.reload_camera_stream)
                self.feed_cards[stream_key] = card
                row, col = grid_position_for_feed(slot_index)
                feed_layout.addWidget(card, row, col)

            for row in range(2):
                feed_layout.setRowStretch(row, 1)
            for col in range(2):
                feed_layout.setColumnStretch(col, 1)

        self.content_layout.addWidget(feed_area, 1)

        pagination = QHBoxLayout()
        pagination.addStretch(1)
        self.prev_page_button = QPushButton("‹")
        self.next_page_button = QPushButton("›")
        for button, tooltip in (
            (self.prev_page_button, "Previous page"),
            (self.next_page_button, "Next page"),
        ):
            button.setToolTip(tooltip)
            button.setFixedSize(34, 30)
            button.setStyleSheet("""
                QPushButton {
                    font-size: 18px;
                    font-weight: 700;
                    line-height: 30px;
                    padding: 0;
                    text-align: center;
                }
            """)
        self.prev_page_button.clicked.connect(self.show_previous_page)
        self.next_page_button.clicked.connect(self.show_next_page)
        self.prev_page_button.setEnabled(self.current_page > 0)
        self.next_page_button.setEnabled(self.current_page < max_page)
        pagination.addWidget(self.prev_page_button)
        pagination.addWidget(self.next_page_button)
        pagination.addStretch(1)
        self.content_layout.addLayout(pagination)

    def show_previous_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.show_feed_dashboard()

    def show_next_page(self):
        if self.current_page < (len(self.camera_entries) - 1) // FEEDS_PER_PAGE:
            self.current_page += 1
            self.show_feed_dashboard()

    def open_feed_detail(self, ip: str):
        if ip not in self.active_devices:
            return

        self._clear_content()
        title = QLabel(f"Camera Detail - {self.display_name_for_ip(ip)}")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #d7e1ea;")
        self.content_layout.addWidget(title)

        detail_row = QHBoxLayout()
        detail_row.setSpacing(14)

        video_panel = QFrame()
        video_panel.setObjectName("videoPanel")
        video_panel.setStyleSheet("""
            QFrame#videoPanel {
                background: #13202c;
                border: 1px solid #26394d;
                border-radius: 8px;
            }
        """)
        video_layout = QVBoxLayout(video_panel)
        video_layout.setContentsMargins(10, 10, 10, 10)
        ptz_service = self.get_ptz_service(ip)
        display_widget = CameraDisplayWidget(
            ip=ip,
            show_ptz=True,
            fixed_size=False,
            ptz_service=ptz_service,
            ptz_supported=ptz_service is not None,
        )
        stream_key = self.stream_key(ip, "detail")
        self.display_widgets[stream_key] = display_widget
        self.start_camera_display_stream(ip, "detail")
        video_layout.addWidget(display_widget)

        controls_panel = self._build_detail_controls(ip)
        detail_row.addWidget(video_panel, 1)
        detail_row.addWidget(controls_panel)
        self.content_layout.addLayout(detail_row, 1)

    def get_ptz_service(self, ip: str):
        if ip in self.ptz_services:
            return self.ptz_services[ip]
        device = self.active_devices.get(ip)
        if not device or not device.capability.ptz_supported:
            return None
        try:
            service = OnvifPTZService(ip=ip, user=device.username or "admin", pwd=device.password)
        except Exception as exc:
            print(f"PTZ Disabled for {ip}: {exc}")
            return None
        self.ptz_services[ip] = service
        return service

    def _build_detail_controls(self, ip: str) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(390)
        panel.setObjectName("controlsPanel")
        panel.setStyleSheet("""
            QFrame#controlsPanel {
                background: #1d2a36;
                border: 1px solid #405468;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        device = self.active_devices[ip]

        record_button = QPushButton("Record")
        record_button.setMinimumHeight(74)
        record_button.setStyleSheet(STYLE_RECORD_BTN_DEFAULT)
        record_button.clicked.connect(partial(self.toggle_recording, ip))
        layout.addWidget(record_button)
        self.active_record_buttons[ip] = record_button

        status_label = QLabel(device.status.name.title())
        status_label.setObjectName("detailStreamStatus")
        layout.addWidget(status_label)
        self.stream_status_labels[self.stream_key(ip, "detail")] = status_label

        reload_button = QPushButton("Reload Stream")
        reload_button.setObjectName("reloadDetailStreamButton")
        reload_button.clicked.connect(partial(self.reload_camera_stream, ip, "detail"))
        layout.addWidget(reload_button)

        snapshot_button = QPushButton("Snapshot")
        snapshot_button.setEnabled(False)
        live_button = QPushButton("Live View")
        live_button.setEnabled(False)
        action_row = QHBoxLayout()
        action_row.addWidget(snapshot_button)
        action_row.addWidget(live_button)
        layout.addLayout(action_row)

        profiles = device.capability.valid_profiles()
        if profiles:
            profile_selector = QComboBox()
            profile_selector.setToolTip("Select the RTSP media profile used by this detail view.")
            profile_selector.setMinimumHeight(32)
            profile_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            profile_selector.setMinimumContentsLength(28)
            for profile in sorted(profiles, key=lambda item: (item.pixels, item.name)):
                label = profile.label()
                profile_selector.addItem(label, profile.token)
                profile_selector.setItemData(profile_selector.count() - 1, label, Qt.ItemDataRole.ToolTipRole)
            current = device.capability.detail_profile(device.selected_detail_profile)
            if current:
                index = profile_selector.findData(current.token)
                if index >= 0:
                    profile_selector.setCurrentIndex(index)
            profile_selector.currentIndexChanged.connect(partial(self.change_detail_profile, ip, profile_selector))
            layout.addWidget(profile_selector)

        controls_title = QLabel("Camera Controls")
        controls_title.setStyleSheet("background: #405468; color: #d7e1ea; font-weight: 700; padding: 8px;")
        layout.addWidget(controls_title)
        for label in ("Motion Detection", "Night Vision", "IR Illumination"):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            toggle = QPushButton("Unavailable")
            toggle.setEnabled(False)
            row.addWidget(toggle)
            layout.addLayout(row)

        details_title = QLabel("Camera Technical Details")
        details_title.setStyleSheet("background: #405468; color: #d7e1ea; font-weight: 700; padding: 8px;")
        layout.addWidget(details_title)

        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setFrameShape(QFrame.Shape.NoFrame)
        details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        details_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        details_scroll.setViewportMargins(0, 0, 10, 0)
        details_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        details_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                width: 16px;
            }
        """)
        details_container = QWidget()
        details_layout = QVBoxLayout(details_container)
        details_layout.setContentsMargins(0, 0, 8, 0)
        details_layout.setSpacing(6)

        detail_profile = device.capability.detail_profile(device.selected_detail_profile)
        video = detail_profile.video if detail_profile else None
        audio = detail_profile.audio if detail_profile else None
        device_info = device.capability.device_info
        details = {
            "Name": self.display_name_for_ip(ip),
            "IP Address": ip,
            "ONVIF": self._format_device_identity(device_info),
            "Profile": detail_profile.name if detail_profile else "Fallback RTSP",
            "Resolution": f"{detail_profile.width}x{detail_profile.height}" if detail_profile and detail_profile.width else f"{WIDTH}x{HEIGHT}",
            "Video": video.codec if video and video.codec else "Unknown",
            "FPS": str(video.fps) if video and video.fps else "Unknown",
            "Audio": audio.codec if audio and audio.codec else "Unavailable",
            "Recording Audio": self._format_recording_audio_mode(device.capability.recording_audio_mode),
            "PTZ": "Available" if device.capability.ptz_supported else "Unavailable",
            "Status": device.status.name.title(),
        }
        for label, value in details.items():
            details_layout.addLayout(self._make_detail_row(label, value))

        if device.capability.warnings:
            warnings = "\n".join(device.capability.warnings[:4])
            warning_label = QLabel(warnings)
            warning_label.setWordWrap(True)
            warning_label.setToolTip("\n".join(device.capability.warnings))
            warning_label.setStyleSheet("color: #e4c069;")
            details_layout.addWidget(warning_label)

        details_layout.addStretch(1)
        details_scroll.setWidget(details_container)
        layout.addWidget(details_scroll, 1)
        return panel

    def _make_detail_row(self, label: str, value: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        label_widget = QLabel(f"{label}:")
        label_widget.setFixedWidth(118)
        label_widget.setFixedHeight(28)
        label_widget.setToolTip(label)
        label_widget.setStyleSheet("background: #152331; padding: 4px;")

        value_label = QLabel(value)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setToolTip(value)
        value_label.setFixedHeight(28)
        value_label.setMinimumWidth(0)
        value_label.setStyleSheet("background: #152331; padding: 4px;")
        value_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        row.addWidget(label_widget)
        row.addWidget(value_label, 1)
        return row

    def _format_device_identity(self, info: dict) -> str:
        manufacturer = info.get("manufacturer") or "Unknown"
        model = info.get("model") or ""
        return f"{manufacturer} {model}".strip()

    def _format_recording_audio_mode(self, mode: str) -> str:
        if mode == "rtsp":
            return "RTSP"
        if mode == "legacy_tcp":
            return "Legacy TCP"
        return "Unknown"

    def change_detail_profile(self, ip: str, selector: QComboBox, _index: int):
        token = selector.currentData()
        if not token:
            return
        device = self.active_devices.get(ip)
        entry = self.camera_entries.get(ip)
        if not device or not entry:
            return
        device.selected_detail_profile = token
        entry.selected_detail_profile = token
        self.stream_manager.stop_stream(self.stream_key(ip, "detail"))
        self.start_camera_display_stream(ip, "detail")
        self.save_cached_cameras()

    def reload_camera_stream(self, ip: str, usage: str = "preview"):
        device = self.active_devices.get(ip)
        if not device:
            return
        stream_key = self.stream_key(ip, usage)
        device.status = ConnectionStatus.RELOADING
        self.on_stream_status_changed(stream_key, ConnectionStatus.RELOADING)
        self.stream_manager.stop_stream(stream_key)
        entry = self.camera_entries.get(ip)
        if entry:
            self.refresh_capability_async(entry)
        self.start_camera_display_stream(ip, usage)

    def show_settings_screen(self, selected_tab: str = "Configured Cameras"):
        self._clear_content()
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #d7e1ea;")
        self.content_layout.addWidget(title)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #405468;
                background: #13202c;
            }
        """)
        tabs.addTab(self._build_configured_cameras_tab(), "Configured Cameras")
        tabs.addTab(self._build_networks_tab(), "Networks")
        if selected_tab == "Networks":
            tabs.setCurrentIndex(1)
        self.content_layout.addWidget(tabs, 1)

    def show_network_settings(self, add_network: bool = False):
        self.show_new_network_row = add_network
        self.show_settings_screen("Networks")

    def _build_configured_cameras_tab(self) -> QWidget:
        container = QWidget()
        layout = QGridLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        headers = ["ID", "IP Address", "Display Name", "Username", "Password", "Status", "Order", ""]
        for col, header in enumerate(headers):
            label = QLabel(header)
            label.setStyleSheet("font-weight: 700; color: #d7e1ea;")
            layout.addWidget(label, 0, col)

        entries = self.sorted_camera_entries()
        if not entries:
            empty_label = QLabel("No configured cameras.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty_label, 1, 0, 1, len(headers))
        else:
            for row, entry in enumerate(entries, start=1):
                id_label = QLabel(str(entry.id))
                ip_input = QLineEdit(entry.ip)
                name_input = QLineEdit(entry.display_name)
                username_input = QLineEdit(entry.username)
                password_input = QLineEdit(entry.password)
                password_input.setEchoMode(QLineEdit.EchoMode.Password)
                status = self.active_devices.get(entry.ip)
                status_label = QLabel(status.status.name.title() if status else "Disconnected")

                up_button = QPushButton("↑")
                down_button = QPushButton("↓")
                up_button.setFixedWidth(34)
                down_button.setFixedWidth(34)
                up_button.setEnabled(row > 1)
                down_button.setEnabled(row < len(entries))
                up_button.clicked.connect(partial(self.move_camera_entry, entry.ip, -1))
                down_button.clicked.connect(partial(self.move_camera_entry, entry.ip, 1))

                order_row = QHBoxLayout()
                order_row.addWidget(up_button)
                order_row.addWidget(down_button)

                save_button = QPushButton("Save")
                save_button.clicked.connect(partial(
                    self.save_camera_settings,
                    entry.ip,
                    ip_input,
                    name_input,
                    username_input,
                    password_input,
                ))

                layout.addWidget(id_label, row, 0)
                layout.addWidget(ip_input, row, 1)
                layout.addWidget(name_input, row, 2)
                layout.addWidget(username_input, row, 3)
                layout.addWidget(password_input, row, 4)
                layout.addWidget(status_label, row, 5)
                layout.addLayout(order_row, row, 6)
                layout.addWidget(save_button, row, 7)

        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.setRowStretch(max(1, len(entries) + 1), 1)
        return container

    def _build_networks_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        add_button = QPushButton("Add Network")
        add_button.clicked.connect(partial(self.show_network_settings, True))
        action_row.addWidget(add_button)
        layout.addLayout(action_row)

        profiles = self.network_profile_repository.list()
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        headers = ["Network Range", "SSID", "Password", "", "", ""]
        for col, header in enumerate(headers):
            label = QLabel(header)
            label.setStyleSheet("font-weight: 700; color: #d7e1ea;")
            grid.addWidget(label, 0, col)

        next_row = 1
        if profiles:
            for row, profile in enumerate(profiles, start=1):
                network_range = profile["network_range"]
                credentials = self.credentials_store.get_wifi_credentials(network_range)
                ssid = credentials.ssid if credentials else profile.get("ssid", "")
                password = credentials.password if credentials else ""

                range_input = QLineEdit(network_range)
                ssid_input = QLineEdit(ssid)
                password_input = QLineEdit(password)
                password_input.setEchoMode(QLineEdit.EchoMode.Password)

                save_button = QPushButton("Save")
                save_button.clicked.connect(
                    partial(self.save_network_profile, network_range, range_input, ssid_input, password_input)
                )
                setup_button = QPushButton("Generate Ginatex QR")
                setup_button.clicked.connect(
                    partial(
                        self.generate_network_qr,
                        range_input,
                        ssid_input,
                        password_input,
                    )
                )
                delete_button = QPushButton("Delete")
                delete_button.clicked.connect(partial(self.delete_network_profile, network_range))

                grid.addWidget(range_input, row, 0)
                grid.addWidget(ssid_input, row, 1)
                grid.addWidget(password_input, row, 2)
                grid.addWidget(save_button, row, 3)
                grid.addWidget(setup_button, row, 4)
                grid.addWidget(delete_button, row, 5)
                next_row = row + 1

        if self.show_new_network_row:
            range_input = QLineEdit(DEFAULT_SCAN_RANGE if not profiles else "")
            ssid_input = QLineEdit("")
            password_input = QLineEdit("")
            password_input.setEchoMode(QLineEdit.EchoMode.Password)
            save_button = QPushButton("Save")
            save_button.clicked.connect(
                partial(self.save_network_profile, "", range_input, ssid_input, password_input)
            )

            grid.addWidget(range_input, next_row, 0)
            grid.addWidget(ssid_input, next_row, 1)
            grid.addWidget(password_input, next_row, 2)
            grid.addWidget(save_button, next_row, 3)
            next_row += 1
        elif not profiles:
            empty_label = QLabel("No saved networks. Add a network before scanning.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(empty_label, 1, 0, 1, len(headers))

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)

        layout.addStretch(1)
        return container

    def save_camera_settings(
        self,
        old_ip: str,
        ip_input: QLineEdit,
        name_input: QLineEdit,
        username_input: QLineEdit,
        password_input: QLineEdit,
    ):
        new_ip = ip_input.text().strip()
        display_name = name_input.text().strip()
        username = username_input.text().strip()
        password = password_input.text()

        try:
            ip_address(new_ip)
        except ValueError:
            QMessageBox.warning(self, "Invalid IP Address", "Enter a valid camera IP address.")
            return
        if not display_name:
            QMessageBox.warning(self, "Display Name Required", "Enter a display name for the camera.")
            return
        if new_ip != old_ip and new_ip in self.camera_entries:
            QMessageBox.warning(self, "Duplicate IP Address", "A configured camera already uses that IP address.")
            return

        entry = self.camera_entries.get(old_ip)
        if not entry:
            return

        if new_ip == old_ip:
            entry.display_name = display_name
            entry.username = username
            entry.password = password
            device = self.active_devices.get(old_ip)
            if device:
                device.name = display_name
                device.username = username
                device.password = password
            self.save_cached_cameras()
            self.refresh_capability_async(entry)
            self.show_settings_screen()
            return

        self.stop_camera_stream(old_ip)
        device = self.active_devices.pop(old_ip, CameraDevice(ip=new_ip, status=ConnectionStatus.CONNECTING))
        recorder = self.active_recorders.pop(old_ip, PyAVRecorderService())
        self.display_widgets.pop(self.stream_key(old_ip, "preview"), None)
        self.display_widgets.pop(self.stream_key(old_ip, "detail"), None)
        self.feed_cards.pop(self.stream_key(old_ip, "preview"), None)
        self.stream_status_labels.pop(self.stream_key(old_ip, "detail"), None)
        self.active_record_buttons.pop(old_ip, None)
        self.ptz_services.pop(old_ip, None)

        entry.ip = new_ip
        entry.display_name = display_name
        entry.username = username
        entry.password = password
        self.camera_entries.pop(old_ip, None)
        self.camera_entries[new_ip] = entry

        device.ip = new_ip
        device.name = display_name
        device.username = username
        device.password = password
        device.status = ConnectionStatus.CONNECTING
        self.active_devices[new_ip] = device
        self.active_recorders[new_ip] = recorder
        self.save_cached_cameras()
        self.refresh_capability_async(entry)
        self.show_settings_screen()

    def move_camera_entry(self, ip: str, direction: int):
        entries = self.sorted_camera_entries()
        index = next((idx for idx, entry in enumerate(entries) if entry.ip == ip), None)
        if index is None:
            return
        target_index = index + direction
        if target_index < 0 or target_index >= len(entries):
            return

        entries[index].id, entries[target_index].id = entries[target_index].id, entries[index].id
        self.save_cached_cameras()
        self.show_settings_screen()

    def save_network_profile(
        self,
        old_range: str,
        range_input: QLineEdit,
        ssid_input: QLineEdit,
        password_input: QLineEdit,
    ):
        try:
            network_range = normalize_network_range(range_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Network Range", str(exc))
            return

        ssid = ssid_input.text().strip()
        password = password_input.text()
        credentials_missing = False
        if self.credentials_store.is_available:
            credentials_missing = not self.credentials_store.set_wifi_credentials(
                network_range,
                StoredWifiCredentials(ssid=ssid, password=password),
            )
        elif password:
            credentials_missing = True

        if old_range and old_range != network_range:
            self.credentials_store.delete_wifi_credentials(old_range)
        self.network_profile_repository.update(network_range, ssid, credentials_missing=credentials_missing)
        self.show_new_network_row = False
        self.show_settings_screen("Networks")

    def delete_network_profile(self, network_range: str):
        confirm = QMessageBox.question(
            self,
            "Delete Network",
            f"Delete saved network {network_range} and its stored Wi-Fi credentials?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.network_profile_repository.delete(network_range)
        self.credentials_store.delete_wifi_credentials(network_range)
        self.show_network_settings()

    def generate_network_qr(
        self,
        range_input: QLineEdit,
        ssid_input: QLineEdit,
        password_input: QLineEdit,
    ):
        try:
            network_range = normalize_network_range(range_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Network Range", str(exc))
            return

        ssid = ssid_input.text().strip()
        if not ssid:
            QMessageBox.warning(self, "SSID Required", "Enter the Wi-Fi network name.")
            return

        adapter = GinatexQrProvisioningAdapter()
        payload = adapter.create_payload(
            ssid=ssid,
            password=password_input.text(),
            network_range=network_range,
        )
        self.show_network_qr_dialog(
            network_range,
            self._make_qr_pixmap(adapter.qr_text(payload), 320),
            protocol_label=adapter.display_name,
        )

    def show_network_qr_dialog(self, network_range: str, pixmap: QPixmap, protocol_label: str = "Ginatex QR"):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{protocol_label} Setup - {network_range}")
        dialog.setModal(True)
        dialog.setMinimumWidth(380)

        layout = QVBoxLayout(dialog)
        title = QLabel(f"{protocol_label} provisioning")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_label.setPixmap(pixmap)
        layout.addWidget(qr_label)

        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        dialog.exec()

    def _make_qr_pixmap(self, text: str, size: int) -> QPixmap:
        return make_qr_pixmap(text, size)

    def get_configured_scan_range(self) -> str | None:
        for profile in self.network_profile_repository.list():
            try:
                return normalize_network_range(profile["network_range"])
            except (KeyError, TypeError, ValueError) as exc:
                print(f"Unable to read configured scan range: {exc}")
        return None

    def run_background_scan(self):
        network_range = self.get_configured_scan_range()
        if not network_range:
            self.show_network_settings(add_network=True)
            return

        self.is_scanning_network = True
        self.scan_button.setEnabled(False)
        self.scan_button.setText("Scan Network")
        if not self.active_devices:
            self.show_feed_dashboard()

        worker = DiscoveryWorker(self.discovery_service, self.enrichment_service, network_range)
        worker.signals.camera_found.connect(self.on_camera_discovered)
        worker.signals.finished.connect(self.on_scan_finished)
        worker.signals.error.connect(self.on_scan_error)

        self.thread_pool.start(worker)

    def on_camera_discovered(self, discovered):
        ip, capability = discovered if isinstance(discovered, tuple) else (discovered, CameraCapability())
        self.add_camera(ip, capability=capability)

    def on_scan_finished(self):
        self.is_scanning_network = False
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Scan Network")
        if not self.active_devices:
            self.show_feed_dashboard()

    def on_scan_error(self, error_msg: str):
        self.is_scanning_network = False
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Scan Network")
        if not self.active_devices:
            self.show_feed_dashboard()
        print(f"Discovery Error: {error_msg}")

    def stop_camera_stream(self, ip: str):
        if hasattr(self.stream_manager, "stop_stream"):
            self.stream_manager.stop_stream(self.stream_key(ip, "preview"))
            self.stream_manager.stop_stream(self.stream_key(ip, "detail"))

    def add_camera(
        self,
        ip: str,
        persist: bool = True,
        cache_entry: CameraCacheEntry | None = None,
        capability: CameraCapability | None = None,
    ):
        if ip in self.active_devices:
            if capability:
                self.on_capability_refreshed((ip, capability))
            return

        entry = cache_entry or self.camera_entries.get(ip)
        if not entry:
            entry = CameraCacheEntry(id=self.next_camera_cache_id(), ip=ip, display_name=ip)
        if capability:
            entry.capability = capability
        self.camera_entries[ip] = entry

        device = CameraDevice(
            ip=ip,
            name=entry.display_name,
            username=entry.username,
            password=entry.password,
            status=ConnectionStatus.CONNECTING,
            capability=entry.capability,
            selected_preview_profile=entry.selected_preview_profile,
            selected_detail_profile=entry.selected_detail_profile,
        )
        recorder_service = PyAVRecorderService()

        self.active_devices[ip] = device
        self.active_recorders[ip] = recorder_service

        if entry.capability.stale:
            self.refresh_capability_async(entry)
        if persist:
            self.save_cached_cameras()
            self.show_feed_dashboard()

    def on_capability_refreshed(self, refreshed):
        ip, capability = refreshed
        entry = self.camera_entries.get(ip)
        device = self.active_devices.get(ip)
        if entry:
            entry.capability = capability
            if not entry.selected_preview_profile:
                preview = capability.preview_profile()
                entry.selected_preview_profile = preview.token if preview else ""
            if not entry.selected_detail_profile:
                detail = capability.detail_profile()
                entry.selected_detail_profile = detail.token if detail else ""
        if device:
            device.capability = capability
            if entry:
                device.selected_preview_profile = entry.selected_preview_profile
                device.selected_detail_profile = entry.selected_detail_profile
        for usage in ("preview", "detail"):
            stream_key = self.stream_key(ip, usage)
            if stream_key in self.display_widgets:
                self.stream_manager.stop_stream(stream_key)
                self.start_camera_display_stream(ip, usage)
        self.save_cached_cameras()

    def on_frame_received(self, stream_key: str, stream_frame):
        ip = stream_key.split(":", 1)[0]
        device = self.active_devices.get(ip)
        if device:
            device.status = ConnectionStatus.CONNECTED
        self.stream_manager.set_status(stream_key, ConnectionStatus.CONNECTED, self.on_stream_status_changed)

        display_widget = self.display_widgets.get(stream_key)
        if display_widget:
            rgb_data = self.stream_service.convert_for_ui(stream_frame.data)
            h, w, ch = rgb_data.shape
            bytes_per_line = ch * w
            qt_img = QImage(rgb_data.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            display_widget.set_frame(QPixmap.fromImage(qt_img))

        record_button = self.active_record_buttons.get(ip)
        if record_button:
            if stream_frame.is_recording:
                record_button.setText("Stop Recording")
                record_button.setStyleSheet(STYLE_RECORD_BTN_ACTIVE)
            else:
                record_button.setText("Record")
                record_button.setStyleSheet(STYLE_RECORD_BTN_DEFAULT)

    def on_stream_status_changed(self, stream_key: str, status: ConnectionStatus):
        ip = stream_key.split(":", 1)[0]
        device = self.active_devices.get(ip)
        if device:
            device.status = status

        display_widget = self.display_widgets.get(stream_key)
        if display_widget:
            display_widget.set_status(status.name.title())

        feed_card = self.feed_cards.get(stream_key)
        if feed_card:
            feed_card.set_status(status)

        status_label = self.stream_status_labels.get(stream_key)
        if status_label:
            status_label.setText(status.name.title())

    def toggle_recording(self, ip: str):
        recorder = self.active_recorders.get(ip)
        if not recorder:
            return
        if recorder.is_recording:
            recorder.stop()
        else:
            self.handle_record_request(ip)

    def handle_record_request(self, ip: str):
        dlg = RecordDialog(ip, self)

        if dlg.exec() == int(QDialog.DialogCode.Accepted):
            request = dlg.get_request()
            recorder = self.active_recorders.get(ip)
            device = self.active_devices.get(ip)

            if recorder and device:
                recorder.start(
                    rtsp_url=device.recording_stream_url,
                    output_path=request.output_path,
                    duration_minutes=request.duration_minutes,
                    use_rtsp_audio=device.recording_uses_rtsp_audio,
                )

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Q:
            self.close()

    def request_quit(self, confirm: bool = True):
        self._skip_close_confirmation = not confirm
        self.close()

    def shutdown(self):
        if self._shutdown_started:
            return

        self._shutdown_started = True
        self.save_cached_ips()

        for recorder in list(self.active_recorders.values()):
            recorder.stop()

        for widget in list(self.display_widgets.values()):
            widget.stop_motors()

        self.stream_manager.stop_all()

    def closeEvent(self, event):
        if self._skip_close_confirmation:
            reply = QMessageBox.StandardButton.Yes
        else:
            reply = QMessageBox.question(
                self,
                "Exit?",
                "Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

        if reply == QMessageBox.StandardButton.Yes:
            self.shutdown()
            event.accept()
        else:
            event.ignore()
