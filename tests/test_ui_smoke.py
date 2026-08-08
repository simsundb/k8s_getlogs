import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_main_window_constructs(app):
    from src.ui.main_window import MainWindow
    win = MainWindow()
    assert win.stack.count() == 3
    assert win.nav.count() == 3
    win.close()


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
