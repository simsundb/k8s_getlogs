import sys

from PySide6.QtWidgets import QApplication

from src.config import APP_DIR
from src.logger import setup_logging
from src.ui.main_window import MainWindow


def main():
    setup_logging(APP_DIR / "logs")
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
