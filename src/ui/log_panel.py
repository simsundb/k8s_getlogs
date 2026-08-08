# src/ui/log_panel.py
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QPlainTextEdit


class LogPanel(QPlainTextEdit):
    """只读滚动日志面板，自动滚到底部，限制最大行数防内存暴涨。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        # 等宽字体（Windows=Consolas / macOS=Menlo）：kubectl/df 等对齐输出列对齐
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        # 长行不折行：内容超出宽度时出现横向滚动条；行数超出时纵向滚动条自动出现
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def append_log(self, text: str) -> None:
        self.appendPlainText(text)
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear_log(self) -> None:
        self.clear()
