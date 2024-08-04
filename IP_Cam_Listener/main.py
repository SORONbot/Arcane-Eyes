import sys
import traceback
import os
import cv2
from PyQt6.QtCore import *
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import *


os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"

camera_1_address = 'rtsp://192.168.100.25:554'
camera_2_address = 'rtsp://192.168.100.24:554'

width = 640
height = 480


def is_camera_available(address):
    cap = cv2.VideoCapture(address)
    is_opened = cap.isOpened()
    cap.release()
    return is_opened


def resize_and_maintain_aspect_ratio(orig_width, orig_height, img_res):
    # Get the aspect ratio
    aspect_ratio = orig_width / orig_height

    # Calculate downscale size
    if orig_width > orig_height:
        new_width = width
        new_height = int(width / aspect_ratio)
    else:
        new_height = height
        new_width = int(width * aspect_ratio)

    # Resize the frame
    new_img_res = cv2.resize(img_res, (new_width, new_height))

    return new_img_res


def convert_cv_to_qt(cv_img):
    rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    cv_img_height, cv_img_width, channels = rgb_image.shape
    bytes_per_line = channels * cv_img_width
    qt_img = QImage(rgb_image.data, cv_img_width, cv_img_height, bytes_per_line, QImage.Format.Format_RGB888)
    return qt_img


class CustomDialog(QMessageBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exit?")
        self.setText("Are you sure you want to exit?")
        self.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        self.setIcon(QMessageBox.Icon.Question)


class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        tuple (exctype, value, traceback.format_exc() )

    result
        object data returned from processing, anything

    """

    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    stop = pyqtSignal()


class CameraWorker(QRunnable):
    def __init__(self, address, *args, **kwargs):
        super(CameraWorker, self).__init__()
        self.args = args
        self.kwargs = kwargs
        self.address = address
        self.signals = WorkerSignals()
        self.stop_flag = False

        self.kwargs['stop_callback'] = self.signals.stop

        self.signals.stop.connect(self.stop_worker)

    def stop_worker(self):
        self.stop_flag = True  # Set the flag to stop the worker

    @pyqtSlot()
    def run(self):
        try:
            # Get the stream from the camera
            camera_stream = cv2.VideoCapture(self.address)

            while not self.stop_flag:
                # Read the stream
                is_frame_from_camera_ok, cam_img_res = camera_stream.read()

                if is_frame_from_camera_ok:
                    # Get the Height and Width of the frame
                    cam_original_height, cam_original_width = cam_img_res.shape[:2]

                    # Call the function to resize the frame but keep aspect ratio
                    frame = resize_and_maintain_aspect_ratio(cam_original_width, cam_original_height, cam_img_res)

                    # Emit the result signal with the resized frame
                    self.signals.result.emit(frame)
                else:
                    print("Failed to capture image")
                    traceback.print_exc()
                    exctype, value = sys.exc_info()[:2]
                    self.signals.error.emit((exctype, value, traceback.format_exc()))

            camera_stream.release()
        except Exception as e:
            print("Error occurred in worker")
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Camera Feeds")
        self.setGeometry(100, 100, width * 2, height)

        layout = QHBoxLayout()

        self.camera_feed_1_layout = QVBoxLayout()
        self.camera_feed_2_layout = QVBoxLayout()

        self.camera_feed_1 = QLabel(self)
        self.camera_feed_1.setStyleSheet("background-color: black;")
        self.camera_feed_1.setFixedSize(width, height)

        self.camera_feed_2 = QLabel(self)
        self.camera_feed_2.setStyleSheet("background-color: black;")
        self.camera_feed_2.setFixedSize(width, height)

        self.camera_feed_1_title = QLabel("Camera Feed 1", self)
        self.camera_feed_1_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_feed_1_title.setStyleSheet("font-weight: bold; color: white; background-color: gray;")

        self.camera_feed_2_title = QLabel("Camera Feed 2", self)
        self.camera_feed_2_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_feed_2_title.setStyleSheet("font-weight: bold; color: white; background-color: gray;")

        self.camera_feed_1_layout.addWidget(self.camera_feed_1_title)
        self.camera_feed_1_layout.addWidget(self.camera_feed_1)

        self.camera_feed_2_layout.addWidget(self.camera_feed_2_title)
        self.camera_feed_2_layout.addWidget(self.camera_feed_2)

        layout.addLayout(self.camera_feed_1_layout)
        layout.addLayout(self.camera_feed_2_layout)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.thread_pool = QThreadPool()
        print("Multithreading with maximum %d threads" % self.thread_pool.maxThreadCount())

        # Set up the workers and connect signals to slots

        if is_camera_available(camera_1_address):
            self.camera_worker_1 = CameraWorker(camera_1_address)
            self.thread_pool.start(self.camera_worker_1)
            self.camera_worker_1.signals.result.connect(self.update_camera_feed_1)
        else:
            print("Camera 1 not available")

        if is_camera_available(camera_2_address):
            self.camera_worker_2 = CameraWorker(camera_2_address)
            self.thread_pool.start(self.camera_worker_2)
            self.camera_worker_2.signals.result.connect(self.update_camera_feed_2)
        else:
            print("Camera 2 not available")

    def update_camera_feed_1(self, frame):
        qt_img = convert_cv_to_qt(frame)
        self.camera_feed_1.setPixmap(QPixmap.fromImage(qt_img))

    def update_camera_feed_2(self, frame):
        qt_img = convert_cv_to_qt(frame)
        self.camera_feed_2.setPixmap(QPixmap.fromImage(qt_img))

    def keyPressEvent(self, event):
        if event.key() == 81:
            self.close()

    def closeEvent(self, event):
        dlg = CustomDialog(self)
        result = dlg.exec()

        if result == QMessageBox.StandardButton.Yes:
            # Signal the workers to stop
            if hasattr(self, 'camera_worker_1'):
                self.camera_worker_1.signals.stop.emit()
            if hasattr(self, 'camera_worker_2'):
                self.camera_worker_2.signals.stop.emit()

            # Ensure threads are finished
            self.thread_pool.waitForDone()

            event.accept()
        else:
            event.ignore()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())
