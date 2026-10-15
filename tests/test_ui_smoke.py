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


def test_collect_page_has_no_aggregate_checkbox(app, monkeypatch, tmp_path):
    """②页汇总不再是可选项：结果一律落 logs_collected/<日期>/，故开关已移除。"""
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from src.ui.collect_page import CollectPage
    page = CollectPage(lambda: [])
    try:
        assert not hasattr(page, "aggregate_cb")
    finally:
        page.deleteLater()


def test_collect_worker_leaves_only_logs_collected(app, monkeypatch, tmp_path):
    """工作线程收尾接线：采集结果只落 logs_collected/<日期>/，中间目录树清掉、不产 zip。"""
    import tarfile

    from src.models import CollectTask, PodMeta
    from src.ui.collect_page import _CollectWorker

    remote = tmp_path / "remote"
    remote.mkdir()
    (remote / "hycommon.log").write_text("one", encoding="utf-8")

    class FakeSSH:
        def exec_stdout(self, command, timeout=60):
            return 0, "__TAR_OK__\n", ""

        def stream_to_file(self, command, filepath, timeout=600):
            with tarfile.open(filepath, "w:gz") as tf:
                for p in sorted(remote.rglob("*")):
                    if p.is_file():
                        tf.add(p, arcname=p.relative_to(remote))
            return 0

        def close(self):
            pass

    out_dir = tmp_path / "output"
    collect_base = out_dir / "2026-10-15"
    dest = out_dir / "logs_collected" / "2026-10-15"
    task = CollectTask(pod_name="podX", deploy_name="app", namespace="ns",
                       pattern="*.log")
    metas = [PodMeta(name="podX", namespace="ns", deploy_name="app")]

    worker = _CollectWorker([task], metas, collect_base, "ns",
                            lambda: FakeSSH(), dest_dir=dest)
    worker.start()
    assert worker.wait(20000)

    assert worker.aggregate["files"] == 1
    assert (dest / "app_hycommon.log").read_text(encoding="utf-8") == "one"
    assert (dest / "pods_manifest.json").exists()
    assert not collect_base.exists()
    assert list(out_dir.rglob("*.zip")) == []


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
