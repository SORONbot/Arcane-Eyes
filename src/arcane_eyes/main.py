import sys
import os
from dotenv import load_dotenv

load_dotenv()

from PyQt6.QtCore import Qt, QThreadPool, pyqtSlot, QRunnable, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout,
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
from arcane_eyes.services.discovery_service import NetworkDiscoveryService
from arcane_eyes.services.stream_service import StreamService
from arcane_eyes.services.recorder_service import PyAVRecorderService

# Import Custom UI Widgets
from arcane_eyes.ui.camera_widget import CameraDisplayWidget
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
        self.thread_pool = QThreadPool()

        # State Tracking
        self.active_devices = {}  # ip -> CameraDevice
        self.active_recorders = {}  # ip -> PyAVRecorderService
        self.display_widgets = {}  # ip -> CameraDisplayWidget
        self.cam_count = 0

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

        self.scan_button = QPushButton("Scan Network for Eyes")
        self.scan_button.clicked.connect(self.run_background_scan)
        self.main_layout.addWidget(self.scan_button)

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