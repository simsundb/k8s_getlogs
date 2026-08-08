import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from src.config import APP_DIR
from src.logger import setup_logging
from src.ui.icons import combo_arrow_qss
from src.ui.main_window import MainWindow
from src.ui.style import APP_STYLE


def _resource_path(name: str) -> str:
    """源码运行时取项目根；冻结运行时取 PyInstaller 解包目录 _MEIPASS。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return str(base / "assets" / name)


def _center_on_screen(app, win) -> None:
    """窗口居中并自适应屏幕：按主屏可用区（排除任务栏）clamp 尺寸再居中。"""
    screen = app.primaryScreen()
    if screen is None:
        return
    geo = screen.availableGeometry()
    win.resize(min(win.width(), geo.width()), min(win.height(), geo.height()))
    frame = win.frameGeometry()
    frame.moveCenter(geo.center())
    win.move(frame.topLeft())


def main():
    setup_logging(APP_DIR / "logs")
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE + combo_arrow_qss())
    app.setWindowIcon(QIcon(_resource_path("app_icon.png")))
    win = MainWindow()
    win.show()
    _center_on_screen(app, win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
