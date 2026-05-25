from arcane_eyes.core.models import ConnectionStatus
from arcane_eyes.logic.stream_manager import StreamManager


def test_stream_manager_reports_error_and_finished_statuses():
    manager = StreamManager()
    statuses = []

    manager._handle_error("192.168.100.20:preview", lambda key, status: statuses.append((key, status)), Exception("boom"))
    manager._handle_finished("192.168.100.21:preview", lambda key, status: statuses.append((key, status)))

    assert statuses == [
        ("192.168.100.20:preview", ConnectionStatus.ERROR),
        ("192.168.100.21:preview", ConnectionStatus.OFFLINE),
    ]


def test_stopped_stream_finished_does_not_report_offline():
    manager = StreamManager()
    statuses = []
    manager._stopping.add("192.168.100.20:preview")

    manager._handle_finished("192.168.100.20:preview", lambda key, status: statuses.append((key, status)))

    assert statuses == []
