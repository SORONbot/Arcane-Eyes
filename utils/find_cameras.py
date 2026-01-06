import socket
from contextlib import closing


def check_camera(address: str):
    host = address.split(":")[1].split("//")[1]
    port = int(address.split(":")[2])

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        if sock.connect_ex((host, port)) == 0:
            return True
        return False
