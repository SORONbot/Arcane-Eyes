import time
from threading import Thread

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

from arcane_eyes.services.provisioning_service import CameraAdoptionService


class AdoptionWorkerSignals(QObject):
    progress = pyqtSignal(int)
    camera_adopted = pyqtSignal(str)
    timeout = pyqtSignal()
    error = pyqtSignal(str)
    finished = pyqtSignal()


class CameraAdoptionWorker(QRunnable):
    def __init__(
        self,
        adoption_service: CameraAdoptionService,
        known_ips,
        timeout_seconds: float = 180,
        network_range: str | None = None,
    ):
        super().__init__()
        self.adoption_service = adoption_service
        self.known_ips = set(known_ips)
        self.timeout_seconds = timeout_seconds
        self.network_range = network_range
        self.signals = AdoptionWorkerSignals()
        self._is_running = True

    @pyqtSlot()
    def run(self):
        start_time = time.monotonic()
        ticker = Thread(target=self._emit_countdown, args=(start_time,), daemon=True)
        ticker.start()

        try:
            ip = self.adoption_service.wait_for_new_camera(
                known_ips=self.known_ips,
                timeout_seconds=self.timeout_seconds,
                should_stop=lambda: not self._is_running,
                network_range=self.network_range,
            )
            if not self._is_running:
                return
            if ip:
                self.signals.camera_adopted.emit(ip)
            else:
                self.signals.timeout.emit()
        except Exception as e:
            if self._is_running:
                self.signals.error.emit(str(e))
        finally:
            self._is_running = False
            ticker.join(timeout=0.2)
            self.signals.finished.emit()

    def _emit_countdown(self, start_time: float):
        last_remaining = None
        while self._is_running:
            elapsed = time.monotonic() - start_time
            remaining = max(0, int(self.timeout_seconds - elapsed))
            if remaining != last_remaining:
                self.signals.progress.emit(remaining)
                last_remaining = remaining
            if remaining <= 0:
                return
            time.sleep(0.2)

    def stop(self):
        self._is_running = False
