import cv2
from PyQt6.QtCore import QRunnable, pyqtSlot, QObject, pyqtSignal
from arcane_eyes.core.models import StreamFrame
from arcane_eyes.core.exceptions import CameraAppError


class WorkerSignals(QObject):
    frame_ready = pyqtSignal(StreamFrame)
    error = pyqtSignal(CameraAppError)
    finished = pyqtSignal()


class CameraWorker(QRunnable):
    """
    The engine for an individual camera stream.
    Focuses on the high-speed capture loop and dispatches frames to services.
    """

    def __init__(self, camera_device, stream_service, recorder_service):
        super().__init__()
        self.device = camera_device
        self.stream_service = stream_service
        self.recorder_service = recorder_service
        self.signals = WorkerSignals()
        self._is_running = True

    @pyqtSlot()
    def run(self):
        cap = cv2.VideoCapture(self.device.rtsp_url)

        try:
            while self._is_running:
                success, frame = cap.read()
                if not success:
                    break

                # Use services to process and check recording state
                is_rec = self.recorder_service.is_recording
                processed_frame = self.stream_service.process_frame(frame, is_recording=is_rec)

                # Emit the bundled StreamFrame model to the UI
                self.signals.frame_ready.emit(processed_frame)

        except Exception as e:
            self.signals.error.emit(CameraAppError(f"Stream interrupted: {e}", ip=self.device.ip))
        finally:
            cap.release()
            self.signals.finished.emit()

    def stop(self):
        self._is_running = False