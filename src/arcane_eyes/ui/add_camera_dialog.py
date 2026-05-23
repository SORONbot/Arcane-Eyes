from io import BytesIO

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
import qrcode

from arcane_eyes.core.config import DEFAULT_SCAN_RANGE
from arcane_eyes.services.provisioning_service import (
    SetupQrCredentialCache,
    WifiProvisioningPayload,
    normalize_network_range,
)


class AddCameraDialog(QDialog):
    provisioning_started = pyqtSignal(object)
    retry_requested = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, parent=None, credential_cache: SetupQrCredentialCache | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add Camera")
        self.setMinimumWidth(460)
        self.payload = None
        self.credential_cache = credential_cache or SetupQrCredentialCache()

        self._setup_ui()
        self._load_cached_credentials()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.network_range_input = QLineEdit(DEFAULT_SCAN_RANGE)
        self.network_range_input.setPlaceholderText("192.168.100.0/24")
        self.network_range_input.editingFinished.connect(self._load_cached_credentials)

        self.ssid_input = QLineEdit()
        self.ssid_input.setPlaceholderText("Wi-Fi network name")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Leave empty for open networks")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Network range", self.network_range_input)
        form.addRow("SSID", self.ssid_input)
        form.addRow("Password", self.password_input)
        layout.addLayout(form)

        self.qr_label = QLabel("Enter Wi-Fi credentials to generate setup QR.")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setFixedSize(360, 360)
        layout.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel(self._initial_status_text())
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        self.start_button = QPushButton("Generate QR & Start")
        self.retry_button = QPushButton("Retry Scan")
        self.cancel_button = QPushButton("Cancel")

        self.retry_button.setEnabled(False)
        self.start_button.clicked.connect(self._on_start_clicked)
        self.retry_button.clicked.connect(self.retry_requested.emit)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)

        button_row.addWidget(self.start_button)
        button_row.addWidget(self.retry_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

    def _initial_status_text(self) -> str:
        status = f"Waiting to scan {DEFAULT_SCAN_RANGE}."
        if self.credential_cache.warning:
            return f"{status} {self.credential_cache.warning}"
        return status

    def _load_cached_credentials(self):
        try:
            network_range = normalize_network_range(self.network_range_input.text())
        except ValueError:
            return

        try:
            credentials = self.credential_cache.load(network_range)
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return

        if credentials:
            self.ssid_input.setText(credentials.ssid)
            self.password_input.setText(credentials.password)
            self.status_label.setText(f"Loaded saved Wi-Fi credentials for {network_range}.")

    def _on_start_clicked(self):
        try:
            network_range = normalize_network_range(self.network_range_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Network Range Required", str(exc))
            return

        ssid = self.ssid_input.text().strip()
        if not ssid:
            QMessageBox.warning(self, "SSID Required", "Enter the Wi-Fi network name.")
            return

        password = self.password_input.text()
        self.payload = WifiProvisioningPayload(
            ssid=ssid,
            password=password,
            network_range=network_range,
        )
        self._show_qr(self.payload.to_qr_text())
        self._save_cached_credentials(network_range, ssid, password)
        self.set_scanning_state()
        self.provisioning_started.emit(self.payload)

    def _save_cached_credentials(self, network_range: str, ssid: str, password: str):
        try:
            saved = self.credential_cache.save(network_range, ssid, password)
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return

        if not saved and self.credential_cache.warning:
            print(self.credential_cache.warning)
            self.status_label.setText(self.credential_cache.warning)

    def get_network_range(self) -> str:
        if self.payload:
            return self.payload.network_range
        return normalize_network_range(self.network_range_input.text())

    def _show_qr(self, text: str):
        image = qrcode.make(text)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")
        self.qr_label.setPixmap(
            pixmap.scaled(
                self.qr_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _on_cancel_clicked(self):
        self.cancelled.emit()
        self.reject()

    def set_scanning_state(self):
        self.network_range_input.setEnabled(False)
        self.ssid_input.setEnabled(False)
        self.password_input.setEnabled(False)
        self.start_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        network_range = self.payload.network_range if self.payload else self.network_range_input.text().strip()
        status = f"Show this QR to the reset camera. Scanning {network_range} for RTSP stream..."
        if self.credential_cache.warning:
            status = f"{status} {self.credential_cache.warning}"
        self.status_label.setText(status)

    def set_progress(self, remaining_seconds: int):
        network_range = self.payload.network_range if self.payload else self.network_range_input.text().strip()
        self.status_label.setText(
            f"Show this QR to the camera. Scanning {network_range} for a new RTSP stream... "
            f"{remaining_seconds}s left."
        )

    def set_success(self, ip: str):
        self.status_label.setText(f"Camera adopted at {ip}.")
        self.retry_button.setEnabled(False)
        self.cancel_button.setText("Close")

    def set_timeout(self):
        self.status_label.setText("No new RTSP stream found. Keep the QR visible and retry scanning.")
        self.retry_button.setEnabled(True)
        self.start_button.setEnabled(False)

    def set_error(self, error_message: str):
        self.status_label.setText(f"Adoption error: {error_message}")
        self.retry_button.setEnabled(True)

    def closeEvent(self, event):
        self.cancelled.emit()
        super().closeEvent(event)
