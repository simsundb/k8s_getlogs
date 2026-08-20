import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QHeaderView, QPlainTextEdit,
                               QPushButton)


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


def test_collect_page_default_storage_dir_is_software_dir(app, monkeypatch, tmp_path):
    """②页默认存储目录 = 软件所在目录；config 指定 output_dir 时跟随。"""
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from src.config import software_dir
    from src.ui.collect_page import CollectPage
    page = CollectPage(lambda: [])
    try:
        assert page.out_dir == software_dir()
    finally:
        page.deleteLater()


def test_collect_page_aggregate_checkbox_default_checked(app, monkeypatch, tmp_path):
    """②页汇总开关默认勾选，取消勾选后持久化到 config.json。"""
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from src.ui.collect_page import CollectPage
    page = CollectPage(lambda: [])
    try:
        assert page.aggregate_cb.isChecked() is True
        page.aggregate_cb.setChecked(False)
        from src.config import load_config
        assert load_config()["aggregate_after_collect"] is False
    finally:
        page.deleteLater()


def test_log_panel_uses_fixed_pitch_font(app, monkeypatch, tmp_path):
    """④页运维输出等宽字体：kubectl/df 对齐输出列对齐可读。"""
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from src.ui.log_panel import LogPanel
    panel = LogPanel()
    try:
        family = panel.font().family().lower()
        assert any(k in family for k in ("mono", "consolas", "courier", "menlo", "monaco"))
    finally:
        panel.deleteLater()


def test_icons_load_and_apply(app, monkeypatch, tmp_path):
    """图标资源存在且能给按钮设置图标（资源缺失会返回空图标，也不应崩溃）。"""
    from src.ui.icons import combo_arrow_qss, icon, set_icon
    for name, color in [("server", "accent"), ("download", "white")]:
        qicon = icon(name, color)
        assert not qicon.isNull(), f"图标缺失: {name}/{color}.png"
    qss = combo_arrow_qss()
    assert "chevron-down" in qss and "url(" in qss   # 下拉箭头图标片段已生成
    # 源图 40px，QSS 必须显式缩小（16px），否则箭头在下拉区里过大
    assert "width: 16px" in qss and "height: 16px" in qss
    btn = QPushButton()
    try:
        set_icon(btn, "refresh-cw")
        assert not btn.icon().isNull()
        assert not btn.iconSize().isEmpty()
        set_icon(btn, "不存在的图标")      # 缺失时静默降级
        assert btn.iconSize().isEmpty() is False
    finally:
        btn.deleteLater()


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
