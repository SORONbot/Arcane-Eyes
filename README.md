# 👁️ Arcane Eyes

A service-oriented IP camera management application. Arcane Eyes provides high-performance RTSP streaming, PTZ (Pan-Tilt-Zoom) control via ONVIF, and dual-stream A/V recording.

Arcane Eyes is designed to replace fragmented, proprietary software suites with a unified, open-source platform for managing commercial and consumer-grade IP cameras. 
By leveraging standard protocols and common network configurations, the application provides a centralized control panel to monitor live feeds, execute synchronized recordings, and manage Pan-Tilt-Zoom (PTZ) hardware across all discovered devices. 

## 🚀 Key Features
* **Live Discovery**: Async network scanning that populates your UI the moment a camera is found.
* **Smart Caching**: Remembers your cameras in `.eye_cache` to skip scanning on next launch.
* **Clean Recordings**: Wait-for-keyframe logic and PTS rebasing to prevent green smearing in MP4s.
* **Dual-Stream Audio**: Captures video via RTSP and synchronized raw audio via TCP/8001.

## 🛠️ Installation & Setup

This project uses **uv** for ultra-fast dependency management and building.

1. **Clone and Install:**
   ```bash
   uv pip install -e .
   ```

2. **Run With:**
    ```bash
    arcane-eyes
    ```
---

## Next Steps

- Proper Control Panel
- Better layout management for multiple cameras (4+)
- Proper Setup Sequence for New Cameras
- Support for modifying internal configurations for cameras
- PTZ support for cameras that do not use ONVIF