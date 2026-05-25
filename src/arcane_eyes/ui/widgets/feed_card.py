from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from arcane_eyes.core.models import ConnectionStatus


class FeedCard(QFrame):
    def __init__(
        self,
        ip: str,
        display_name: str,
        display_widget,
        on_open,
        on_reload,
        parent=None,
    ):
        super().__init__(parent)
        self.ip = ip
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("feedCard")
        self.setStyleSheet("""
            QFrame#feedCard {
                border: 1px solid #405468;
                border-radius: 8px;
                background: #1d2a36;
            }
            QFrame#feedCard:hover {
                border-color: #6f8fac;
                background: #223242;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel(display_name)
        title.setStyleSheet("font-weight: 700; color: #d7e1ea; background: transparent; border: none;")
        layout.addWidget(title)
        ip_label = QLabel(ip)
        ip_label.setStyleSheet("color: #9fb0bf; background: transparent; border: none;")
        layout.addWidget(ip_label)

        status_row = QHBoxLayout()
        self.status_label = QLabel("Connecting")
        self.status_label.setObjectName("streamStatus")
        self.status_label.setStyleSheet("color: #9fb0bf; background: transparent; border: none;")
        status_row.addWidget(self.status_label, 1)
        reload_button = QPushButton("Reload")
        reload_button.setObjectName("reloadStreamButton")
        reload_button.setToolTip("Reload stream")
        reload_button.clicked.connect(lambda: on_reload(self.ip, "preview"))
        status_row.addWidget(reload_button)
        layout.addLayout(status_row)
        layout.addWidget(display_widget, 1)

        self._on_open = on_open

    def set_status(self, status: ConnectionStatus):
        self.status_label.setText(status.name.title())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_open(self.ip)
        super().mousePressEvent(event)
