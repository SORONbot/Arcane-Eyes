from PyQt6.QtCore import QPointF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

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
        margin = 12
        icon_size = 18

        visible_height = min(HEIGHT, int(WIDTH * 9 / 16))
        video_top = max(0, (HEIGHT - visible_height) // 2)
        video_bottom = video_top + visible_height

        controls = [
            ((0, -1), "Tilt up", (WIDTH // 2) - (button_size // 2), video_top + margin, 0, 1),
            ((0, 1), "Tilt down", (WIDTH // 2) - (button_size // 2), video_bottom - button_size - margin, 0, -1),
            ((-1, 0), "Pan left", margin, (HEIGHT // 2) - (button_size // 2), -1, 0),
            ((1, 0), "Pan right", WIDTH - button_size - margin, (HEIGHT // 2) - (button_size // 2), 1, 0)
        ]

        for direction, tooltip, x, y, vx, vy in controls:
            btn = QPushButton(self.video_label)
            btn.setFixedSize(button_size, button_size)
            btn.move(int(x), int(y))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.setIcon(self._make_arrow_icon(*direction, icon_size))
            btn.setIconSize(QSize(icon_size, icon_size))
            btn.setStyleSheet(STYLE_PTZ_BTN)
            btn.raise_()

            btn.pressed.connect(lambda v_x=vx, v_y=vy: self.ptz_service.move(v_x, v_y))
            btn.released.connect(self.ptz_service.stop)

    def _make_arrow_icon(self, dx: int, dy: int, size: int) -> QIcon:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        center = QPointF(size / 2, size / 2)
        direction = QPointF(dx, dy)
        perpendicular = QPointF(-dy, dx)
        start = center - direction * 5
        end = center + direction * 5
        head_a = end - direction * 5 + perpendicular * 4
        head_b = end - direction * 5 - perpendicular * 4

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#20252b"), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(start, end)
        painter.drawLine(end, head_a)
        painter.drawLine(end, head_b)
        painter.end()

        return QIcon(pixmap)

    def stop_motors(self):
        """Called during application shutdown to ensure no cameras are left spinning."""
        if self.ptz_supported and self.ptz_service:
            try:
                self.ptz_service.stop()
            except PTZError:
                pass
