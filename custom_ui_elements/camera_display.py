from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QStyle
from onvif import ONVIFCamera

class PTZController:
    def __init__(self, ip, port=80, user='admin', pwd=''):
        self.ip = ip
        try:
            self.cam = ONVIFCamera(ip, port, user, pwd)
            self.ptz = self.cam.create_ptz_service()
            self.media = self.cam.create_media_service()
            self.token = self.media.GetProfiles()[0].token
            self.active = True
        except Exception as e:
            print(f"PTZ Init failed for {ip}: {e}")
            self.active = False

    def move(self, x, y):
        if not self.active: return
        try:
            self.ptz.ContinuousMove({
                'ProfileToken': self.token,
                'Velocity': {'PanTilt': {'x': x, 'y': y}}
            })
        except: pass

    def stop(self):
        if not self.active: return
        try:
            self.ptz.Stop({'ProfileToken': self.token})
        except: pass

class CameraDisplayWidget(QWidget):
    def __init__(self, ip, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.ptz = PTZController(ip)

        # Main Layout for the label
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Video Label
        self.video_label = QLabel(f"Connecting to {ip}...")
        self.video_label.setFixedSize(640, 480)
        self.video_label.setStyleSheet("background: black; border: 2px solid #333;")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.video_label)

        # Create Overlay Buttons
        self.create_overlay_buttons()

    def create_overlay_buttons(self):
        S = 32  # Button size
        M = 10  # Margin
        W, H = self.video_label.width(), self.video_label.height()

        # Define icons using Qt standard library instead of text strings
        # Format: (IconEnum, x, y, vx, vy)
        controls = [
            (QStyle.StandardPixmap.SP_ArrowUp, (W // 2) - (S // 2), M, 0, 1),
            (QStyle.StandardPixmap.SP_ArrowDown, (W // 2) - (S // 2), H - S - M, 0, -1),
            (QStyle.StandardPixmap.SP_ArrowLeft, M, (H // 2) - (S // 2), -1, 0),
            (QStyle.StandardPixmap.SP_ArrowRight, W - S - M, (H // 2) - (S // 2), 1, 0)
        ]

        for icon_enum, x, y, vx, vy in controls:
            btn = QPushButton(self.video_label)
            btn.setFixedSize(S, S)
            btn.move(int(x), int(y))

            # Set the icon and ensure it's centered
            icon = self.style().standardIcon(icon_enum)
            btn.setIcon(icon)
            btn.setIconSize(QSize(16, 16))  # Adjust icon size inside the circle

            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(50, 50, 50, 150);
                    border-radius: 16px; /* Half of S */
                    border: none;
                }
                QPushButton:pressed { background-color: rgba(100, 100, 100, 200); }
            """)

            btn.pressed.connect(lambda v_x=vx, v_y=vy: self.ptz.move(v_x, v_y))
            btn.released.connect(self.ptz.stop)