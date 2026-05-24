from PyQt6.QtCore import QPointF, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QSizePolicy

from arcane_eyes.core.constants import WIDTH, HEIGHT, STYLE_PTZ_BTN
from arcane_eyes.core.exceptions import PTZError


class VideoLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self._source_pixmap = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_frame(self, pixmap: QPixmap):
        self._source_pixmap = pixmap
        self.update()

    def content_rect(self) -> QRect:
        if not self._source_pixmap or self._source_pixmap.isNull():
            return self.rect()

        scaled_size = self._source_pixmap.size()
        scaled_size.scale(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x = (self.width() - scaled_size.width()) // 2
        y = (self.height() - scaled_size.height()) // 2
        return QRect(x, y, scaled_size.width(), scaled_size.height())

    def paintEvent(self, event):
        if not self._source_pixmap or self._source_pixmap.isNull():
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#13202c"))
        painter.drawPixmap(self.content_rect(), self._source_pixmap)


class CameraDisplayWidget(QWidget):
    """
    UI Component for displaying a single camera feed and its PTZ controls.
    """
    def __init__(self, ip: str, parent=None, show_ptz: bool = True, fixed_size: bool = False, ptz_service=None, ptz_supported: bool = False):
        super().__init__(parent)
        self.ip = ip
        self.show_ptz = show_ptz
        self.fixed_size = fixed_size
        self.ptz_service = ptz_service
        self.ptz_supported = ptz_supported and ptz_service is not None
        self.ptz_buttons = []

        self._setup_ui()

    def _setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Video Label bounded by constants
        self.video_label = VideoLabel(f"Connecting to {self.ip}...")
        self.video_label.setStyleSheet("background: #13202c;")
        if self.fixed_size:
            self.video_label.setFixedSize(WIDTH, HEIGHT)
            self.setFixedSize(WIDTH, HEIGHT)
        else:
            self.video_label.setMinimumSize(1, 1)
            self.video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.layout.addWidget(self.video_label)

        # Only draw overlay controls if the camera actually supports them
        if self.show_ptz and self.ptz_supported:
            self._create_overlay_buttons()

    def set_frame(self, pixmap: QPixmap):
        self.video_label.set_frame(pixmap)
        self._position_ptz_buttons()

    def _create_overlay_buttons(self):
        button_size = 32
        icon_size = 18

        controls = [
            ("top", (0, -1), "Tilt up", 0, 1),
            ("bottom", (0, 1), "Tilt down", 0, -1),
            ("left", (-1, 0), "Pan left", -1, 0),
            ("right", (1, 0), "Pan right", 1, 0),
        ]

        for edge, direction, tooltip, vx, vy in controls:
            btn = QPushButton(self.video_label)
            btn.setFixedSize(button_size, button_size)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.setIcon(self._make_arrow_icon(*direction, icon_size))
            btn.setIconSize(QSize(icon_size, icon_size))
            btn.setStyleSheet(STYLE_PTZ_BTN)
            btn.raise_()

            btn.pressed.connect(lambda v_x=vx, v_y=vy: self.ptz_service.move(v_x, v_y))
            btn.released.connect(self.ptz_service.stop)
            self.ptz_buttons.append((edge, btn))

        self._position_ptz_buttons()

    def _position_ptz_buttons(self):
        if not self.ptz_buttons:
            return

        button_size = 32
        margin = 12
        rect = self.video_label.content_rect()
        center_x = rect.left() + (rect.width() - button_size) // 2
        center_y = rect.top() + (rect.height() - button_size) // 2
        positions = {
            "top": (center_x, rect.top() + margin),
            "bottom": (center_x, rect.bottom() - button_size - margin + 1),
            "left": (rect.left() + margin, center_y),
            "right": (rect.right() - button_size - margin + 1, center_y),
        }

        for edge, btn in self.ptz_buttons:
            x, y = positions[edge]
            btn.move(max(0, int(x)), max(0, int(y)))
            btn.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_ptz_buttons()

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
