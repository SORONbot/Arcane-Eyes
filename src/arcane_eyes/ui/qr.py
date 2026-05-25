from io import BytesIO

import qrcode
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap


def make_qr_pixmap(text: str, size: int) -> QPixmap:
    image = qrcode.make(text)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")
    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
