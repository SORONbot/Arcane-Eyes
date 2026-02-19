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
        background-color: rgba(50, 50, 50, 150);
        border-radius: 16px;
        border: none;
    }
    QPushButton:pressed { 
        background-color: rgba(100, 100, 100, 200); 
    }
"""