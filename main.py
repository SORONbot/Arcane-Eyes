import ipaddress
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor

import cv2
from PyQt6.QtCore import *
from PyQt6.QtGui import QPixmap, QImage, QKeyEvent
from PyQt6.QtWidgets import *

from utils import check_camera, CameraScanner

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"

cam_scanner = CameraScanner()

width = 640
height = 480


def is_camera_available(address):
    if check_camera(address):
        cap = cv2.VideoCapture(address)
        is_opened = cap.isOpened()
        cap.release()
        return is_opened

    return False


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


class ScannerSignals(QObject):
    # Emits the IP address as soon as one is found
    camera_found = pyqtSignal(str)
    # Notifies when the entire network scan is done
    finished = pyqtSignal()


class ScanWorker(QRunnable):
    def __init__(self, scanner_instance, network_range):
        super().__init__()
        self.scanner = scanner_instance
        self.network_range = network_range
        self.signals = ScannerSignals()

    @pyqtSlot()
    def run(self):
        # We modify the logic slightly to emit signals during the loop
        network = ipaddress.IPv4Network(self.network_range)

        with ThreadPoolExecutor(max_workers=50) as executor:
            ip_list = [str(ip) for ip in network]
            # We use executor.map just like you did
            results = executor.map(check_camera, ip_list)

            for ip, is_camera in zip(ip_list, results):
                if is_camera:
                    self.scanner.found_cameras.append(ip)
                    # Tell the UI we found one!
                    self.signals.camera_found.emit(ip)

        self.signals.finished.emit()


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
        self.scanner = CameraScanner()
        self.camera_workers = []
        self.active_ips = set()

        # UI Setup
        self.central_widget = QWidget()
        self.main_vbox = QVBoxLayout(self.central_widget)

        # Scan Button
        self.scan_button = QPushButton("Scan for New Cameras")
        self.scan_button.clicked.connect(self.run_background_scan)
        self.main_vbox.addWidget(self.scan_button)

        # UI setup for the Camera Feeds
        self.grid_widget = QWidget()
        self.layout = QGridLayout(self.grid_widget)
        self.main_vbox.addWidget(self.grid_widget)

        self.setCentralWidget(self.central_widget)

        self.thread_pool = QThreadPool()
        self.cam_count = 0

        # Run initial scan
        self.run_background_scan()

    def run_background_scan(self):
        # Create the worker
        worker = ScanWorker(self.scanner, "192.168.100.0/24")
        # Connect the signal to our UI update function
        worker.signals.camera_found.connect(self.setup_new_camera)
        self.thread_pool.start(worker)

    def setup_new_camera(self, ip):
        """Called every time the scanner finds a camera"""
        if ip in self.active_ips:
            print(f"Skipping {ip}, already active.")
            return

        self.active_ips.add(ip)

        rtsp_url = f"rtsp://{ip}:554"

        # 1. Create a Label for the video
        video_label = QLabel(f"Connecting to {ip}...")
        video_label.setFixedSize(width, height)
        video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        video_label.setStyleSheet("background: black; color: white; border: 2px solid #333;")

        # 2. Add to Grid (3 columns wide)
        row = self.cam_count // 3
        col = self.cam_count % 3
        self.layout.addWidget(video_label, row, col)
        self.cam_count += 1

        # 3. Start the CameraStreamWorker (the one that does OpenCV)
        stream_worker = CameraWorker(rtsp_url)
        # Pass the specific video_label using a lambda so the worker knows where to draw
        stream_worker.signals.result.connect(
            lambda frame, lbl=video_label: self.update_frame(frame, lbl)
        )

        self.thread_pool.start(stream_worker)
        self.camera_workers.append(stream_worker)

    def update_frame(self, frame, label):
        """Converts CV frame to Qt and updates the specific label passed in."""
        qt_img = convert_cv_to_qt(frame)
        label.setPixmap(QPixmap.fromImage(qt_img))

    def keyPressEvent(self, event: QKeyEvent):
        # This is more readable than checking for 81
        if event.key() == Qt.Key.Key_Q:
            self.close()

    def closeEvent(self, event):
        """Handles cleanup of all dynamic workers."""
        dlg = CustomDialog(self)
        result = dlg.exec()

        if result == QMessageBox.StandardButton.Yes:
            # Loop through ALL found cameras and signal them to stop
            for worker in self.camera_workers:
                if hasattr(worker.signals, 'stop'):
                    worker.signals.stop.emit()

            # Wait for the thread pool to clean up before exiting
            self.thread_pool.waitForDone()
            event.accept()
        else:
            event.ignore()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())
