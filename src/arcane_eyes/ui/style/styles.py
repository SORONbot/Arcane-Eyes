STYLE_VIDEO_LABEL = "background: black; border: 2px solid #333;"

STYLE_RECORD_BTN_DEFAULT = ""
STYLE_RECORD_BTN_ACTIVE = "background-color: #990000; color: white; font-weight: bold;"

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

APP_QSS = """
QFrame#sidebar {
    background: #243344;
    border-right: 1px solid #33475d;
}
QFrame#sidebar QPushButton {
    min-height: 38px;
    text-align: left;
    padding-left: 14px;
}
QFrame#feedArea,
QFrame#videoPanel {
    background: #13202c;
    border: 1px solid #26394d;
    border-radius: 8px;
}
QFrame#feedCard,
QFrame#controlsPanel {
    background: #1d2a36;
    border: 1px solid #405468;
    border-radius: 8px;
}
QFrame#feedCard:hover {
    background: #223242;
    border-color: #6f8fac;
}
QTabWidget::pane {
    border: 1px solid #405468;
    background: #13202c;
}
"""
