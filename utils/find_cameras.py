import socket
import ipaddress
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor


def check_camera(ip: str, port: int = 554):
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((ip, port)) == 0


class CameraScanner:
    def __init__(self):
        self.found_cameras = []

    def scan_network(self, network_range: str = "192.168.100.0/24"):
        network = ipaddress.IPv4Network(network_range)

        with ThreadPoolExecutor(max_workers=50) as executor:
            # Map the check_camera function to all IPs in the range
            ip_list = [str(ip) for ip in network]
            results = executor.map(check_camera, ip_list)

            # Combine IPs with their True/False results
            for ip, is_camera in zip(ip_list, results):
                if is_camera:
                    print(f"Found Camera: {ip}")
                    self.found_cameras.append(ip)

        return self.found_cameras

    def get_found_cameras_addresses(self, port: int = 554):
        for camera in self.found_cameras:
            yield f"rtsp://{camera}:{port}"
