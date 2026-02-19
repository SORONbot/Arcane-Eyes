import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QSpinBox,
    QDialogButtonBox, QPushButton, QHBoxLayout, QFileDialog
)

from arcane_eyes.core.config import DEFAULT_SAVE_PATH
from arcane_eyes.core.models import RecordingRequest


class RecordDialog(QDialog):
    """
    Modal for configuring video recording parameters.
    Returns a unified RecordingRequest data object.
    """

    def __init__(self, ip: str, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.setWindowTitle(f"Record Feed From: {ip}")

        self.default_name = f"{ip.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp4"
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)

        # File Name
        self.filename_input = QLineEdit(self.default_name)

        # Save Path (Using Professional Config Path)
        # Ensure the directory exists before defaulting to it
        os.makedirs(DEFAULT_SAVE_PATH, exist_ok=True)
        self.path_input = QLineEdit(str(DEFAULT_SAVE_PATH))
        self.path_input.setReadOnly(True)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.select_folder)

        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.browse_btn)

        # Duration input
        self.duration_input = QSpinBox()
        self.duration_input.setRange(1, 120)  # Extended to 2 hours
        self.duration_input.setSuffix(" minutes")
        self.duration_input.setValue(5)

        layout.addRow("Save Directory:", path_layout)
        layout.addRow("File Name:", self.filename_input)
        layout.addRow("Duration:", self.duration_input)

        # Standard Dialog Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Save Directory", str(DEFAULT_SAVE_PATH))
        if folder:
            self.path_input.setText(folder)

    def get_request(self) -> RecordingRequest:
        """Packages the form data into an immutable model."""
        filename = self.filename_input.text().strip()
        if not filename:
            filename = self.default_name
        elif not filename.lower().endswith(".mp4"):
            filename += ".mp4"

        full_path = os.path.join(self.path_input.text(), filename)

        return RecordingRequest(
            target_ip=self.ip,
            output_path=full_path,
            duration_minutes=self.duration_input.value()
        )