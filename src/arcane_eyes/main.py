import sys
import os
from dotenv import load_dotenv

load_dotenv()

from PyQt6.QtCore import Qt, QThreadPool, pyqtSlot, QRunnable, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QMessageBox, QDialog
)

# Import Configs
from arcane_eyes.core.config import DEFAULT_SCAN_RANGE, CACHE_FILE_PATH

# Import Constants (INCLUDING STYLES)
from arcane_eyes.core.constants import (
    WIDTH, HEIGHT, SCAN_TIMEOUT,
    STYLE_RECORD_BTN_ACTIVE, STYLE_RECORD_BTN_DEFAULT
)

# Import Core Models
from arcane_eyes.core.models import CameraDevice

# Import Logic and Services
from arcane_eyes.logic.stream_manager import StreamManager
from arcane_eyes.logic.adoption_worker import CameraAdoptionWorker
from arcane_eyes.services.discovery_service import NetworkDiscoveryService
from arcane_eyes.services.provisioning_service import CameraAdoptionService
from arcane_eyes.services.stream_service import StreamService
from arcane_eyes.services.recorder_service import PyAVRecorderService

# Import Custom UI Widgets
from arcane_eyes.ui.camera_widget import CameraDisplayWidget
from arcane_eyes.ui.add_camera_dialog import AddCameraDialog
from arcane_eyes.ui.record_dialog import RecordDialog


class DiscoveryWorkerSignals(QObject):
    camera_found = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)


class DiscoveryWorker(QRunnable):
    def __init__(self, discovery_service: NetworkDiscoveryService, network_range: str):
        super().__init__()
        self.service = discovery_service
        self.network_range = network_range
        self.signals = DiscoveryWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            self.service.start_async_scan(self.network_range, self.signals.camera_found.emit)
            self.signals.finished.emit()
        except Exception as e:
            self.signals.error.emit(str(e))


class ArcaneEyesMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arcane Eyes")
        self.resize(1280, 720)

        # Initialize Core Services & Managers using Config/Constants
        self.stream_manager = StreamManager()
        self.stream_service = StreamService(target_width=WIDTH, target_height=HEIGHT)
        self.discovery_service = NetworkDiscoveryService(timeout=SCAN_TIMEOUT)
        self.adoption_service = CameraAdoptionService(self.discovery_service)
        self.thread_pool = QThreadPool()

        # State Tracking
        self.active_devices = {}  # ip -> CameraDevice
        self.active_recorders = {}  # ip -> PyAVRecorderService
        self.display_widgets = {}  # ip -> CameraDisplayWidget
        self.cam_count = 0
        self.add_camera_dialog = None
        self.adoption_worker = None

        self._setup_ui()

        # Load the cache first
        self._load_cache()

        # Only auto-scan if no cameras were loaded from the cache
        if not self.active_devices:
            self.run_background_scan()

    def _load_cache(self):
        """Reads the .eye_cache file and restores previous camera sessions."""
        if CACHE_FILE_PATH.exists():
            try:
                with open(CACHE_FILE_PATH, "r") as f:
                    serialized_ips = f.read().strip()

                if serialized_ips:
                    cached_ips = serialized_ips.split(",")
                    for ip in cached_ips:
                        if ip:  # Guard against empty strings
                            self.add_camera(ip)
            except Exception as e:
                print(f"Failed to load .eye_cache: {e}")

    def _save_cache(self):
        """Serializes the currently active IPs into a comma-separated string."""
        try:
            # We only cache the IPs of cameras that successfully connected/were added
            serialized_ips = ",".join(self.active_devices.keys())
            with open(CACHE_FILE_PATH, "w") as f:
                f.write(serialized_ips)
        except Exception as e:
            print(f"Failed to save .eye_cache: {e}")

    def _setup_ui(self):
        self.central_widget = QWidget()
        self.main_layout = QVBoxLayout(self.central_widget)

        button_row = QHBoxLayout()

        self.scan_button = QPushButton("Scan Network for Eyes")
        self.scan_button.clicked.connect(self.run_background_scan)
        button_row.addWidget(self.scan_button)

        self.add_camera_button = QPushButton("Add Camera")
        self.add_camera_button.clicked.connect(self.open_add_camera_dialog)
        button_row.addWidget(self.add_camera_button)

        self.main_layout.addLayout(button_row)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.main_layout.addWidget(self.grid_widget)

        self.setCentralWidget(self.central_widget)

    def run_background_scan(self):
        self.scan_button.setEnabled(False)
        self.scan_button.setText(f"Scanning {DEFAULT_SCAN_RANGE}...")

        worker = DiscoveryWorker(self.discovery_service, DEFAULT_SCAN_RANGE)

        # Connect the live signal directly to the UI addition method
        worker.signals.camera_found.connect(self.add_camera)

        worker.signals.finished.connect(self.on_scan_finished)
        worker.signals.error.connect(self.on_scan_error)

        self.thread_pool.start(worker)

    def on_scan_finished(self):
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Scan Network for Eyes")

    def on_scan_error(self, error_msg: str):
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Scan Network for Eyes")
        print(f"Discovery Error: {error_msg}")

    def open_add_camera_dialog(self):
        self.add_camera_dialog = AddCameraDialog(self)
        self.add_camera_dialog.provisioning_started.connect(self.start_camera_adoption)
        self.add_camera_dialog.retry_requested.connect(self.retry_camera_adoption)
        self.add_camera_dialog.cancelled.connect(self.cancel_camera_adoption)
        self.add_camera_dialog.exec()

    def start_camera_adoption(self, payload=None):
        self.cancel_camera_adoption()

        network_range = DEFAULT_SCAN_RANGE
        if payload and getattr(payload, "network_range", None):
            network_range = payload.network_range
        elif self.add_camera_dialog:
            try:
                network_range = self.add_camera_dialog.get_network_range()
            except ValueError as exc:
                self.add_camera_dialog.set_error(str(exc))
                return

        if self.add_camera_dialog:
            self.add_camera_dialog.set_scanning_state()

        self.adoption_worker = CameraAdoptionWorker(
            adoption_service=self.adoption_service,
            known_ips=self.active_devices.keys(),
            timeout_seconds=180,
            network_range=network_range,
        )
        self.adoption_worker.signals.progress.connect(self.on_adoption_progress)
        self.adoption_worker.signals.camera_adopted.connect(self.on_camera_adopted)
        self.adoption_worker.signals.timeout.connect(self.on_adoption_timeout)
        self.adoption_worker.signals.error.connect(self.on_adoption_error)
        self.adoption_worker.signals.finished.connect(self.on_adoption_finished)
        self.thread_pool.start(self.adoption_worker)

    def retry_camera_adoption(self):
        self.start_camera_adoption()

    def cancel_camera_adoption(self):
        if self.adoption_worker:
            self.adoption_worker.stop()

    def on_adoption_progress(self, remaining_seconds: int):
        if self.add_camera_dialog:
            self.add_camera_dialog.set_progress(remaining_seconds)

    def on_camera_adopted(self, ip: str):
        self.add_camera(ip)
        self._save_cache()

        if self.add_camera_dialog:
            self.add_camera_dialog.set_success(ip)

    def on_adoption_timeout(self):
        if self.add_camera_dialog:
            self.add_camera_dialog.set_timeout()

    def on_adoption_error(self, error_msg: str):
        if self.add_camera_dialog:
            self.add_camera_dialog.set_error(error_msg)
        print(f"Adoption Error: {error_msg}")

    def on_adoption_finished(self):
        self.adoption_worker = None

    def add_camera(self, ip: str):
        if ip in self.active_devices:
            return

        device = CameraDevice(ip=ip)
        recorder_service = PyAVRecorderService()

        self.active_devices[ip] = device
        self.active_recorders[ip] = recorder_service

        container = QWidget()
        container.setFixedWidth(WIDTH + 20)  # Constrain the width to the video size + padding
        v_layout = QVBoxLayout(container)

        display_widget = CameraDisplayWidget(ip=ip)
        self.display_widgets[ip] = display_widget

        record_button = QPushButton("Record")
        # Ensure the button doesn't look weirdly tall or wide
        record_button.setFixedHeight(35)

        def on_record_clicked():
            if recorder_service.is_recording:
                recorder_service.stop()  # Cancel the recording safely
            else:
                self.handle_record_request(ip)

        record_button.clicked.connect(on_record_clicked)

        v_layout.addWidget(display_widget)
        v_layout.addWidget(record_button)

        # 3 columns layout
        row, col = divmod(self.cam_count, 3)
        self.grid_layout.addWidget(container, row, col, Qt.AlignmentFlag.AlignTop)
        self.cam_count += 1

        def on_frame_received(stream_frame):
            rgb_data = self.stream_service.convert_for_ui(stream_frame.data)
            h, w, ch = rgb_data.shape
            bytes_per_line = ch * w

            qt_img = QImage(rgb_data.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            display_widget.video_label.setPixmap(QPixmap.fromImage(qt_img))

            if stream_frame.is_recording:
                record_button.setText("⏹ Stop Recording")
                record_button.setStyleSheet(STYLE_RECORD_BTN_ACTIVE)
            else:
                record_button.setText("Record")
                record_button.setStyleSheet(STYLE_RECORD_BTN_DEFAULT)

        self.stream_manager.start_stream(
            device=device,
            stream_service=self.stream_service,
            recorder_service=recorder_service,
            on_frame_callback=on_frame_received
        )

    def handle_record_request(self, ip: str):
        dlg = RecordDialog(ip, self)

        if dlg.exec() == int(QDialog.DialogCode.Accepted):
            request = dlg.get_request()
            recorder = self.active_recorders.get(ip)
            device = self.active_devices.get(ip)

            if recorder and device:
                recorder.start(
                    rtsp_url=device.rtsp_url,
                    output_path=request.output_path,
                    duration_minutes=request.duration_minutes
                )

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Q:
            self.close()

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, 'Exit?', 'Are you sure you want to exit?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Save the cache right before shutting down!
            self._save_cache()

            self.cancel_camera_adoption()

            for widget in self.display_widgets.values():
                widget.stop_motors()

            self.stream_manager.stop_all()
            event.accept()
        else:
            event.ignore()


def main():
    app = QApplication(sys.argv)
    # Apply a nice dark theme (optional, since you have it in your dependencies)
    import qdarkstyle
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt6())

    window = ArcaneEyesMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()