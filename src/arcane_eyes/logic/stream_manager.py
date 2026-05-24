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

    def start_stream(self, device, stream_service, recorder_service, on_frame_callback):
        """Initializes and starts a worker for a specific camera."""
        if device.ip in self.active_workers:
            return

        worker = CameraWorker(device, stream_service, recorder_service)
        worker.signals.frame_ready.connect(on_frame_callback)

        self.active_workers[device.ip] = worker
        self.thread_pool.start(worker)

    def stop_stream(self, ip: str):
        """Gracefully stop a single camera worker."""
        worker = self.active_workers.pop(ip, None)
        if worker:
            worker.stop()

    def stop_all(self):
        """Graceful shutdown for all camera processes."""
        for worker in self.active_workers.values():
            worker.stop()
        self.thread_pool.waitForDone()
        self.active_workers.clear()
