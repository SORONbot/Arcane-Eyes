import signal
import sys

from dotenv import load_dotenv
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from arcane_eyes.core.config import DATABASE_PATH
from arcane_eyes.logic.stream_manager import StreamManager
from arcane_eyes.services.capability_service import CameraCapabilityEnrichmentService
from arcane_eyes.services.discovery_service import NetworkDiscoveryService
from arcane_eyes.services.storage_service import AppStore
from arcane_eyes.ui.main_window import (
    ArcaneEyesMainWindow,
    CameraCacheEntry,
    FeedCard,
    grid_position_for_feed,
    make_app_icon,
)
from arcane_eyes.ui.style.loader import load_app_stylesheet


def _termination_signals():
    signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        signals.append(signal.SIGHUP)
    return signals


def install_signal_handlers(app: QApplication, window: ArcaneEyesMainWindow):
    def request_shutdown(_signum, _frame):
        window.request_quit(confirm=False)
        app.quit()

    for termination_signal in _termination_signals():
        signal.signal(termination_signal, request_shutdown)

    signal_timer = QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(100)
    app._arcane_signal_timer = signal_timer
    return signal_timer


def main():
    load_dotenv()

    app = QApplication(sys.argv)
    app.setWindowIcon(make_app_icon())
    app.setStyleSheet(load_app_stylesheet())

    window = ArcaneEyesMainWindow()
    app.aboutToQuit.connect(window.shutdown)
    install_signal_handlers(app, window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
