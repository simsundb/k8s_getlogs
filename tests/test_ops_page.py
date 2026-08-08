# tests/test_ops_page.py
"""第④页 SSH 运维页面：构建、命令下拉筛选、描述回显、运行状态与导出开关。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src.ops import OPS_COMMANDS


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _build_page(monkeypatch, tmp_path):
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from src.ui.ops_page import OpsPage
    return OpsPage(lambda: [])


def test_ops_page_constructs_and_lists_all_commands(app, monkeypatch, tmp_path):
    page = _build_page(monkeypatch, tmp_path)
    try:
        assert page.cmd_combo.count() == len(OPS_COMMANDS)
        assert page.cat_combo.itemText(0) == "全部"
        # 导出按钮在无结果时禁用
        assert not page.export_excel_btn.isEnabled()
        assert not page.export_html_btn.isEnabled()
    finally:
        page.deleteLater()


def test_ops_page_category_filter(app, monkeypatch, tmp_path):
    page = _build_page(monkeypatch, tmp_path)
    try:
        cat = "节点"
        page.cat_combo.setCurrentText(cat)
        expect = [c for c in OPS_COMMANDS if c.category == cat]
        assert page.cmd_combo.count() == len(expect)
        for i in range(page.cmd_combo.count()):
            assert page.cmd_combo.itemData(i).category == cat
    finally:
        page.deleteLater()


def test_ops_page_desc_shows_resolved_namespace(app, monkeypatch, tmp_path):
    page = _build_page(monkeypatch, tmp_path)
    try:
        page.cat_combo.setCurrentText("应用")
        page.cmd_combo.setCurrentText("[应用] 命名空间下全部 Pod")
        page.selector.ns_combo.addItem("ns-prod")
        page.selector.ns_combo.setCurrentIndex(0)
        page._show_cmd_desc()
        assert "kubectl get pods -n ns-prod -o wide" in page.cmd_desc.text()
        # 未选命名空间时提示需先选择
        page.selector.ns_combo.clear()
        page._show_cmd_desc()
        assert "需先选择命名空间" in page.cmd_desc.text()
    finally:
        page.deleteLater()


def test_ops_page_run_custom_empty_logs_hint(app, monkeypatch, tmp_path):
    page = _build_page(monkeypatch, tmp_path)
    try:
        page._run_custom()
        text = page.log_panel.toPlainText()
        assert "请先输入要执行的命令" in text
        # 无主机时点预置命令给出引导
        page._run_predefined()
        assert "主机配置" in page.log_panel.toPlainText()
    finally:
        page.deleteLater()


def test_ops_page_export_state_toggles(app, monkeypatch, tmp_path):
    page = _build_page(monkeypatch, tmp_path)
    try:
        from src.ops import OpsResult
        page.results.append(OpsResult(label="x", command="echo 1",
                                      start_time="2026-08-08 10:00:00", ok=True))
        page._update_export_state()
        assert page.export_excel_btn.isEnabled()
        assert page.export_html_btn.isEnabled()
        page._clear()
        assert not page.export_excel_btn.isEnabled()
        assert page.log_panel.toPlainText() == ""
    finally:
        page.deleteLater()
