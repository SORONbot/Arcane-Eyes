WIDTH = 640
HEIGHT = 480
SCAN_TIMEOUT = 0.5

# --- UI Styles ---

# Video Display
STYLE_VIDEO_LABEL = "background: black; border: 2px solid #333;"

# Recording Button States
STYLE_RECORD_BTN_DEFAULT = ""
STYLE_RECORD_BTN_ACTIVE = "background-color: #990000; color: white; font-weight: bold;"

# PTZ Control Buttons
STYLE_PTZ_BTN = """
    QPushButton {
        background-color: rgba(245, 247, 250, 225);
        border: 2px solid rgba(18, 24, 32, 210);
        border-radius: 16px;
        color: #20252b;
        font-size: 20px;
        font-weight: 800;
        padding: 0;
    }
    QPushButton:hover {
        background-color: rgba(255, 255, 255, 245);
        border-color: rgba(0, 0, 0, 235);
        color: #050607;
    }
    QPushButton:pressed {
        background-color: rgba(120, 170, 255, 245);
        border-color: rgba(8, 28, 60, 255);
    }
"""
