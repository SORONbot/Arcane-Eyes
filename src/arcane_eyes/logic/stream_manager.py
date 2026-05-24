from PyQt6.QtCore import QThreadPool
from typing import Dict
from arcane_eyes.logic.camera_worker import CameraWorker


class StreamManager:
    """
    Coordinator for Arcane Eyes.
    Tracks active workers and manages thread safety for multiple camera feeds.
    """

    def __init__(self):
        self.thread_pool = QThreadPool()
        self.active_workers: Dict[str, CameraWorker] = {}

    def start_stream(self, device, stream_service, recorder_service, on_frame_callback, stream_key: str | None = None, stream_url: str | None = None):
        """Initializes and starts a worker for a specific camera."""
        key = stream_key or device.ip
        if key in self.active_workers:
            return

        worker = CameraWorker(device, stream_service, recorder_service, stream_url or device.rtsp_url)
        worker.signals.frame_ready.connect(on_frame_callback)

        self.active_workers[key] = worker
        self.thread_pool.start(worker)

    def stop_stream(self, stream_key: str):
        """Gracefully stop a single camera worker."""
        worker = self.active_workers.pop(stream_key, None)
        if worker:
            worker.stop()

    def stop_all(self):
        """Graceful shutdown for all camera processes."""
        for worker in self.active_workers.values():
            worker.stop()
        self.thread_pool.waitForDone()
        self.active_workers.clear()
