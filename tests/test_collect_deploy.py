# tests/test_collect_deploy.py
"""采集页 Pod 选择：默认全不选、全选=选全部、部署名多选、过滤缩窄、勾选变色。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox

from src.models import DEFAULT_LOG_DIR, PodMeta
from src.ui.style import SELECT_BG


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _build_page(app, monkeypatch, tmp_path, metas):
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from src.ui.collect_page import CollectPage

    monkeypatch.setattr("src.ui.collect_page.get_pods_meta", lambda _client, _ns: metas)
    page = CollectPage(lambda: [])
    page.selector.ns_combo.addItem("ns")
    page.selector.ns_combo.setCurrentIndex(0)   # 触发 currentIndexChanged → _load_pods()
    return page


def _set_deploy_checked(page, deploy, checked):
    """勾选/取消勾选部署名（等效点击下拉里的复选框）。"""
    model = page.deploy_combo.model()
    for r in range(model.rowCount()):
        item = model.item(r)
        if item.text() == deploy:
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            return
    raise AssertionError(f"部署名 {deploy} 不在下拉中")


def test_deploy_combo_populated_from_metas(app, monkeypatch, tmp_path):
    metas = [
        PodMeta(name="ppl2-a", namespace="ns", deploy_name="ppl2"),
        PodMeta(name="ppl2-b", namespace="ns", deploy_name="ppl2"),
        PodMeta(name="web-0", namespace="ns", deploy_name="web"),
    ]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        items = [page.deploy_combo.itemText(i) for i in range(page.deploy_combo.count())]
        assert items == ["ppl2", "web"]                       # 部署名多选下拉（无「全部」项）
        model = page.deploy_combo.model()
        for r in range(model.rowCount()):
            assert model.item(r).checkState() == Qt.Unchecked  # 默认全不勾
    finally:
        page.deleteLater()


def test_default_nothing_selected(app, monkeypatch, tmp_path):
    """默认全部不勾选：直接采集提示无选中。"""
    metas = [PodMeta(name="ppl2-a", namespace="ns", deploy_name="ppl2"),
             PodMeta(name="web-0", namespace="ns", deploy_name="web")]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        for i in range(page.pod_list.count()):
            assert page.pod_list.item(i).checkState() == Qt.Unchecked
        assert page._selected_pods() == []
    finally:
        page.deleteLater()


def test_select_all_and_deselect_all(app, monkeypatch, tmp_path):
    """全选=选择全部 Pod，取消全选=清空。"""
    metas = [PodMeta(name="ppl2-a", namespace="ns", deploy_name="ppl2"),
             PodMeta(name="web-0", namespace="ns", deploy_name="web")]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        page._on_select_all()
        assert set(page._selected_pods()) == {"ppl2-a", "web-0"}
        page._on_deselect_all()
        assert page._selected_pods() == []
    finally:
        page.deleteLater()


def test_toggle_deploy_checks_its_pods(app, monkeypatch, tmp_path):
    """勾选部署名 = 选中该部署下全部 Pod；取消 = 取消该部署全部 Pod。"""
    metas = [PodMeta(name="ppl2-a", namespace="ns", deploy_name="ppl2"),
             PodMeta(name="ppl2-b", namespace="ns", deploy_name="ppl2"),
             PodMeta(name="web-0", namespace="ns", deploy_name="web")]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        _set_deploy_checked(page, "ppl2", True)
        assert page._selected_pods() == ["ppl2-a", "ppl2-b"]
        _set_deploy_checked(page, "ppl2", False)
        assert page._selected_pods() == []
    finally:
        page.deleteLater()


def test_multi_deploy_selection(app, monkeypatch, tmp_path):
    """手动支持选择多个部署名：并集采集。"""
    metas = [PodMeta(name="ppl2-a", namespace="ns", deploy_name="ppl2"),
             PodMeta(name="web-0", namespace="ns", deploy_name="web"),
             PodMeta(name="api-0", namespace="ns", deploy_name="api")]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        _set_deploy_checked(page, "ppl2", True)
        _set_deploy_checked(page, "web", True)
        assert set(page._selected_pods()) == {"ppl2-a", "web-0"}
    finally:
        page.deleteLater()


def test_collection_respects_search_filter_after_select_all(app, monkeypatch, tmp_path):
    """全选后加搜索过滤：采集只取可见的已勾选 Pod。"""
    metas = [PodMeta(name="ppl2-a", namespace="ns", deploy_name="ppl2"),
             PodMeta(name="ppl2-b", namespace="ns", deploy_name="ppl2"),
             PodMeta(name="web-0", namespace="ns", deploy_name="web")]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        page._on_select_all()
        page.search_edit.setText("web")
        assert page._selected_pods() == ["web-0"]
    finally:
        page.deleteLater()


def test_deploy_combo_min_width(app, monkeypatch, tmp_path):
    page = _build_page(app, monkeypatch, tmp_path, [])
    try:
        assert page.deploy_combo.minimumWidth() >= 240
        assert page.deploy_combo.maximumWidth() == 420   # 防被超长项撑破布局
        # 动态填充的下拉应随内容自适应，而不是只在首次显示时定宽
        assert (page.deploy_combo.sizeAdjustPolicy()
                == QComboBox.SizeAdjustPolicy.AdjustToContents)
    finally:
        page.deleteLater()


def test_checked_item_gets_background_color(app, monkeypatch, tmp_path):
    """点击勾选条目背景变色（视觉反馈）。"""
    metas = [PodMeta(name="web-0", namespace="ns", deploy_name="web")]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        item = page.pod_list.item(0)
        item.setCheckState(Qt.Checked)
        assert item.background().color().name().lower() == SELECT_BG.lower()
        item.setCheckState(Qt.Unchecked)
        assert item.background().style() == Qt.BrushStyle.NoBrush  # 无背景
    finally:
        page.deleteLater()


def test_page_default_log_settings(app, monkeypatch, tmp_path):
    """日志目录默认当前目录(/opt/logs)，日志名默认空。"""
    page = _build_page(app, monkeypatch, tmp_path, [])
    try:
        assert page.log_dir_edit.text() == DEFAULT_LOG_DIR
        assert page.log_name_edit.text() == ""
    finally:
        page.deleteLater()


def test_page_build_tasks_uses_log_settings(app, monkeypatch, tmp_path):
    """日志名非空 → 匹配包含该名的 .log；空 → 回落类别模式；目录随输入。"""
    metas = [PodMeta(name="ppl2-a", namespace="ns", deploy_name="ppl2"),
             PodMeta(name="web-0", namespace="ns", deploy_name="web")]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        page.log_dir_edit.setText("/data/logs")
        page.log_name_edit.setText("err")
        page.cat_combo.setCurrentText("hycommon")
        tasks = page._build_tasks("ns", ["ppl2-a"])
        assert tasks[0].log_dir == "/data/logs"
        assert tasks[0].pattern == "*err*.log"           # 日志名覆盖类别模式

        page.log_name_edit.setText("")
        tasks = page._build_tasks("ns", ["web-0"])
        assert tasks[0].pattern == "hycommon*.log"       # 空名回落类别模式
        assert tasks[0].log_dir == "/data/logs"
    finally:
        page.deleteLater()
