# src/ui/style.py
"""全局 QSS 样式表：统一三页配色与控件观感（Windows/macOS 通用）。"""

# 主题色板
ACCENT = "#3b6fc4"      # 主色（蓝）
ACCENT_HOVER = "#2f5ca8"
ACCENT_PRESSED = "#285090"
BG = "#f3f5f9"          # 页面底色
CARD = "#ffffff"        # 卡片/输入底色
BORDER = "#d8dce4"
BORDER_FOCUS = "#6b93d6"
TEXT = "#2b3240"
TEXT_SUB = "#6a7380"
ROW_ALT = "#f6f8fc"
SELECT_BG = "#dfe8f8"
HEADER_BG = "#edf0f6"

APP_STYLE = f"""
QWidget {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
                 "Helvetica Neue", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QWidget {{
    background-color: {BG};
}}
QLabel {{ background: transparent; }}
QGroupBox {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    padding: 12px 10px 10px 10px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {TEXT_SUB};
}}
QPushButton {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 16px;
    min-height: 24px;
    font-weight: normal;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background: #eef2fa; }}
QPushButton:disabled {{ color: {TEXT_SUB}; background: #eef0f4; border-color: #e3e6ec; }}
QPushButton[primary="true"] {{
    background: {ACCENT};
    color: #ffffff;
    border-color: {ACCENT};
    font-weight: bold;
}}
QPushButton[primary="true"]:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton[primary="true"]:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton[primary="true"]:disabled {{ background: #a7b9dc; border-color: #a7b9dc; color: #ffffff; }}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {BORDER_FOCUS}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: none; }}
QComboBox QAbstractItemView {{
    background: {CARD};
    border: 1px solid {BORDER};
    selection-background-color: {SELECT_BG};
    selection-color: {TEXT};
    outline: 0;
}}

QTableWidget, QTableView {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    gridline-color: #e9ecf2;
    alternate-background-color: {ROW_ALT};
}}
QTableWidget::item, QTableView::item {{ padding: 4px 6px; }}
QTableWidget::item:selected, QTableView::item:selected {{
    background: {SELECT_BG};
    color: {TEXT};
}}
QHeaderView::section {{
    background: {HEADER_BG};
    color: {TEXT_SUB};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    font-weight: bold;
}}

QListWidget {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 2px;
}}
QListWidget::item {{ padding: 6px 8px; border-radius: 3px; }}
QListWidget::item:selected {{
    background: {ACCENT};
    color: #ffffff;
}}
QListWidget::item:hover:!selected {{ background: {SELECT_BG}; }}

QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {CARD};
    text-align: center;
    min-height: 18px;
    color: {TEXT};
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

QRadioButton, QCheckBox {{ spacing: 6px; background: transparent; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: #c3cad6; border-radius: 5px; min-height: 30px; margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: #aab4c4; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: #c3cad6; border-radius: 5px; min-width: 30px; margin: 2px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QDialog {{ background: {BG}; }}
QSplitter::handle {{ background: transparent; width: 4px; height: 4px; }}

QStatusBar {{
    background: {CARD};
    border-top: 1px solid {BORDER};
    color: {TEXT_SUB};
}}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {TEXT_SUB}; padding: 0 4px; }}
"""
