def load_app_stylesheet() -> str:
    import qdarkstyle

    from arcane_eyes.ui.style.styles import APP_QSS

    return qdarkstyle.load_stylesheet_pyqt6() + "\n" + APP_QSS
