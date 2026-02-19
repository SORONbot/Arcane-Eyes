import socket
import ipaddress
import cv2
from typing import List, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing

from arcane_eyes.core.interfaces import IDiscoveryService
from arcane_eyes.core.exceptions import DiscoveryError


class NetworkDiscoveryService(IDiscoveryService):
    def __init__(self, timeout: float = 0.5, max_workers: int = 50):
        self.timeout = timeout
        self.max_workers = max_workers

    def _verify_camera(self, ip: str, port: int) -> bool:
        """Internal helper to check socket and OpenCV stream availability."""
        try:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(self.timeout)
                if sock.connect_ex((ip, port)) != 0:
                    return False
        except socket.error:
            return False

        # Suppress OpenCV terminal spam during mass scanning
        import os
        os.environ["OPENCV_LOG_LEVEL"] = "OFF"

        cap = cv2.VideoCapture(f"rtsp://{ip}:{port}")
        is_opened = cap.isOpened()
        cap.release()
        return is_opened

    def scan(self, network_range: str) -> List[str]:
        """Synchronous scan returning all IPs at once at the end."""
        try:
            network = ipaddress.IPv4Network(network_range)
            found_ips = []

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                ip_list = [str(ip) for ip in network]
                results = executor.map(lambda ip: (ip, self._verify_camera(ip, 554)), ip_list)

                for ip, is_open in results:
                    if is_open:
                        found_ips.append(ip)

            return found_ips

        except ValueError as e:
            raise DiscoveryError(f"Invalid network range: {network_range}") from e
        except Exception as e:
            raise DiscoveryError(f"Network scan failed: {str(e)}")

    def start_async_scan(self, network_range: str, on_found: Callable[[str], None]) -> None:
        """
        Executes a scan and triggers a callback immediately for each camera found.
        (Note: This blocks the thread it is called on, so it should be run inside a QRunnable)
        """
        try:
            network = ipaddress.IPv4Network(network_range)
            ip_list = [str(ip) for ip in network]

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all tasks independently and map the Future object to the IP address
                future_to_ip = {
                    executor.submit(self._verify_camera, ip, 554): ip
                    for ip in ip_list
                }

                # as_completed yields futures immediately as they finish
                for future in as_completed(future_to_ip):
                    ip = future_to_ip[future]
                    try:
                        is_camera = future.result()
                        if is_camera:
                            # Trigger the live UI update callback!
                            on_found(ip)
                    except Exception:
                        # If a specific check crashes, ignore it and continue scanning
                        pass

        except ValueError as e:
            raise DiscoveryError(f"Invalid network range: {network_range}") from e
        except Exception as e:
            raise DiscoveryError(f"Async network scan failed: {str(e)}")