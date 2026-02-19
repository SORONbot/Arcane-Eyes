from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QStyle

from arcane_eyes.core.constants import WIDTH, HEIGHT, STYLE_PTZ_BTN
from arcane_eyes.core.exceptions import PTZError
from arcane_eyes.services.ptz_service import OnvifPTZService

class CameraDisplayWidget(QWidget):
    """
    UI Component for displaying a single camera feed and its PTZ controls.
    """
    def __init__(self, ip: str, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.ptz_service = None
        self.ptz_supported = False

        self._init_ptz()
        self._setup_ui()

    def _init_ptz(self):
        """Attempts to initialize the hardware PTZ service."""
        try:
            self.ptz_service = OnvifPTZService(ip=self.ip)
            self.ptz_supported = True
        except PTZError as e:
            # Camera does not support ONVIF/PTZ or wrong credentials
            print(f"PTZ Disabled for {self.ip}: {e}")

    def _setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Video Label bounded by constants
        self.video_label = QLabel(f"Connecting to {self.ip}...")
        self.video_label.setFixedSize(WIDTH, HEIGHT)
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.video_label)

        # Only draw overlay controls if the camera actually supports them
        if self.ptz_supported:
            self._create_overlay_buttons()

    def _create_overlay_buttons(self):
        button_size = 32
        margin = 10

        controls = [
            (QStyle.StandardPixmap.SP_ArrowUp, (WIDTH // 2) - (button_size // 2), margin, 0, 1),
            (QStyle.StandardPixmap.SP_ArrowDown, (WIDTH // 2) - (button_size // 2), HEIGHT - button_size - margin, 0, -1),
            (QStyle.StandardPixmap.SP_ArrowLeft, margin, (HEIGHT // 2) - (button_size // 2), -1, 0),
            (QStyle.StandardPixmap.SP_ArrowRight, WIDTH - button_size - margin, (HEIGHT // 2) - (button_size // 2), 1, 0)
        ]

        for icon_enum, x, y, vx, vy in controls:
            btn = QPushButton(self.video_label)
            btn.setFixedSize(button_size, button_size)
            btn.move(int(x), int(y))

            icon = self.style().standardIcon(icon_enum)
            btn.setIcon(icon)
            btn.setIconSize(QSize(16, 16))

            btn.setStyleSheet(STYLE_PTZ_BTN)

            btn.pressed.connect(lambda v_x=vx, v_y=vy: self.ptz_service.move(v_x, v_y))
            btn.released.connect(self.ptz_service.stop)

    def stop_motors(self):
        """Called during application shutdown to ensure no cameras are left spinning."""
        if self.ptz_supported and self.ptz_service:
            try:
                self.ptz_service.stop()
            except PTZError:
                pass