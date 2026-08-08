"""图标加载：从 assets/icons/<色>/<名>.png 取 QIcon。

源码运行取项目根 assets/；冻结运行取 PyInstaller 解包目录 _MEIPASS/assets/。
图标文件缺失时返回空 QIcon（界面仅少个图标，不报错）。
配色：accent=主色蓝（普通按钮/导航），white=白色（primary 蓝底按钮）。
"""
import sys
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon


def _icons_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "assets" / "icons"


def icon(name: str, color: str = "accent") -> QIcon:
    path = _icons_dir() / color / f"{name}.png"
    return QIcon(str(path)) if path.exists() else QIcon()


def set_icon(btn, name: str, color: str = "accent", size: int = 16) -> None:
    """给按钮设图标并统一图标尺寸，文字旁自动留出图标间距。"""
    btn.setIcon(icon(name, color))
    btn.setIconSize(btn.iconSize().expandedTo(QSize(size, size)))


def combo_arrow_qss() -> str:
    """QComboBox 下拉箭头样式片段：运行时拼绝对路径，源码/冻结包都有效。

    图标缺失时返回空串（QSS 兜底为无箭头，界面不报错）。
    """
    path = _icons_dir() / "accent" / "chevron-down.png"
    if not path.exists():
        return ""
    return f"QComboBox::down-arrow {{ image: url({path}); }}"

