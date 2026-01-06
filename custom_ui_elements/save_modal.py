import os
from time import time

from PyQt6.QtWidgets import QDialog, QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox, QPushButton, QHBoxLayout, \
    QFileDialog
from datetime import datetime


class RecordDialog(QDialog):
    def __init__(self, ip, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Record Feed From: {ip}")
        layout = QFormLayout(self)

        # Default filename: IP + Date
        self.ip = ip
        self.default_name = f"{ip.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        self.filename_input = QLineEdit(self.default_name)

        # Save Path
        self.path_input = QLineEdit(os.getcwd())  # Default to current directory
        self.path_input.setReadOnly(True)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.select_folder)

        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.browse_btn)

        # Duration input (minutes)
        self.duration_input = QSpinBox()
        self.duration_input.setRange(1, 60)
        self.duration_input.setSuffix(" minutes")
        self.duration_input.setValue(5)

        layout.addRow("Save To:", path_layout)
        layout.addRow("File Name:", self.filename_input)
        layout.addRow("Duration:", self.duration_input)

        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if folder:
            self.path_input.setText(folder)

    def get_values(self):
        start_timestamp = time()

        filename = self.filename_input.text().strip()
        if not filename or filename == self.default_name:
            filename = f"{self.ip.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}"

        if not filename.lower().endswith(".mp4"):
            filename += ".mp4"

        full_path = os.path.join(self.path_input.text(), filename)

        return full_path, self.duration_input.value(), start_timestamp