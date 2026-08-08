import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QHeaderView, QPlainTextEdit)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_main_window_constructs(app, monkeypatch, tmp_path):
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from src.ui.main_window import MainWindow
    win = MainWindow()
    assert win.stack.count() == 4
    assert win.nav.count() == 4
    win.close()
    win.deleteLater()


def test_host_page_add_and_delete(app, monkeypatch, tmp_path):
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from src.ui.host_page import HostPage
    page = HostPage()
    page.ip_edit.setText("10.0.0.1")
    page.user_edit.setText("root")
    page.pwd_edit.setText("pw")
    page.add_host()
    assert page.table.rowCount() == 1
    page.table.selectRow(0)
    page.delete_host()
    assert page.table.rowCount() == 0
    page.deleteLater()


def test_host_table_columns_stretch_no_wrap(app, monkeypatch, tmp_path):
    """① 页 4 列铺满整行宽度；超宽不折行、滚动条按需出现。"""
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from src.ui.host_page import HostPage
    page = HostPage()
    try:
        header = page.table.horizontalHeader()
        assert header.sectionResizeMode(0) == QHeaderView.Stretch
        assert page.table.wordWrap() is False
        assert page.table.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded
        assert page.table.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    finally:
        page.deleteLater()


def test_analyze_table_no_wrap_and_scroll(app, monkeypatch, tmp_path):
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from src.ui.analyze_page import AnalyzePage
    page = AnalyzePage(lambda: [])
    try:
        assert page.table.wordWrap() is False
        assert page.table.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    finally:
        page.deleteLater()


def test_log_panel_no_wrap_and_scroll(app, monkeypatch, tmp_path):
    """日志面板长行不折行：超宽出横向滚动条。"""
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from src.ui.collect_page import CollectPage
    page = CollectPage(lambda: [])
    try:
        assert page.log_panel.lineWrapMode() == QPlainTextEdit.NoWrap
        assert page.log_panel.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded
        assert page.log_panel.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    finally:
        page.deleteLater()


def test_center_on_screen_runs(app, monkeypatch, tmp_path):
    """窗口居中 + 屏幕自适应逻辑可执行、尺寸非负。"""
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from main import _center_on_screen
    from src.ui.main_window import MainWindow
    win = MainWindow()
    win.show()
    try:
        _center_on_screen(app, win)
        assert win.width() >= 0 and win.height() >= 0
    finally:
        win.close()
        win.deleteLater()
