from functools import partial
from PyQt6.QtCore import QThreadPool
from typing import Dict
from arcane_eyes.core.models import ConnectionStatus
from arcane_eyes.logic.camera_worker import CameraWorker


class StreamManager:
    """
    Coordinator for Arcane Eyes.
    Tracks active workers and manages thread safety for multiple camera feeds.
    """

    def __init__(self):
        self.thread_pool = QThreadPool()
        self.active_workers: Dict[str, CameraWorker] = {}
        self.stream_statuses: Dict[str, ConnectionStatus] = {}
        self._stopping: set[str] = set()
        self._errored: set[str] = set()

    def start_stream(
        self,
        device,
        stream_service,
        recorder_service,
        on_frame_callback,
        stream_key: str | None = None,
        stream_url: str | None = None,
        on_status_callback=None,
    ):
        """Initializes and starts a worker for a specific camera."""
        key = stream_key or device.ip
        if key in self.active_workers:
            return

        worker = CameraWorker(device, stream_service, recorder_service, stream_url or device.rtsp_url)
        worker.signals.frame_ready.connect(on_frame_callback)
        worker.signals.error.connect(partial(self._handle_error, key, on_status_callback))
        worker.signals.finished.connect(partial(self._handle_finished, key, on_status_callback))

        self.active_workers[key] = worker
        self._stopping.discard(key)
        self._set_status(key, ConnectionStatus.CONNECTING, on_status_callback)
        self.thread_pool.start(worker)

    def stop_stream(self, stream_key: str):
        """Gracefully stop a single camera worker."""
        worker = self.active_workers.pop(stream_key, None)
        if worker:
            self._stopping.add(stream_key)
            worker.stop()
        self.stream_statuses.pop(stream_key, None)

    def set_status(self, stream_key: str, status: ConnectionStatus, on_status_callback=None):
        self._set_status(stream_key, status, on_status_callback)

    def _set_status(self, stream_key: str, status: ConnectionStatus, on_status_callback=None):
        self.stream_statuses[stream_key] = status
        if on_status_callback:
            on_status_callback(stream_key, status)

    def _handle_error(self, stream_key: str, on_status_callback, error):
        self.active_workers.pop(stream_key, None)
        self._stopping.discard(stream_key)
        self._errored.add(stream_key)
        self._set_status(stream_key, ConnectionStatus.ERROR, on_status_callback)

    def _handle_finished(self, stream_key: str, on_status_callback):
        self.active_workers.pop(stream_key, None)
        if stream_key in self._errored:
            self._errored.discard(stream_key)
            return
        if stream_key in self._stopping:
            self._stopping.discard(stream_key)
            return
        self._set_status(stream_key, ConnectionStatus.OFFLINE, on_status_callback)

    def stop_all(self):
        """Graceful shutdown for all camera processes."""
        for key, worker in list(self.active_workers.items()):
            self._stopping.add(key)
            worker.stop()
        self.thread_pool.waitForDone()
        self.active_workers.clear()
        self.stream_statuses.clear()
        self._stopping.clear()
        self._errored.clear()
