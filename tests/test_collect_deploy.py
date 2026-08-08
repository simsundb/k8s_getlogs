# tests/test_collect_deploy.py
"""采集页 Pod 选择：按部署名 / 全选 / 取消全选 / 过滤基础上勾选 / 默认不选。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.models import PodMeta
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


def test_deploy_combo_populated_from_metas(app, monkeypatch, tmp_path):
    metas = [
        PodMeta(name="ppl2-a", namespace="ns", deploy_name="ppl2"),
        PodMeta(name="ppl2-b", namespace="ns", deploy_name="ppl2"),
        PodMeta(name="web-0", namespace="ns", deploy_name="web"),
    ]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        items = [page.deploy_combo.itemText(i) for i in range(page.deploy_combo.count())]
        assert items[0] == "全部"
        assert items[1:] == ["ppl2", "web"]
    finally:
        page.deleteLater()


def test_select_deploy_name_collects_all_its_pods(app, monkeypatch, tmp_path):
    """选中的是部署名：返回该部署名下全部 Pod（ppl2-a 与 ppl2-b 同属 ppl2）。"""
    metas = [
        PodMeta(name="ppl2-a", namespace="ns", deploy_name="ppl2"),
        PodMeta(name="ppl2-b", namespace="ns", deploy_name="ppl2"),
        PodMeta(name="web-0", namespace="ns", deploy_name="web"),
    ]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        page.deploy_combo.setCurrentText("ppl2")
        assert page._selected_pods() == ["ppl2-a", "ppl2-b"]
    finally:
        page.deleteLater()


def test_deploy_all_restores_full_scope(app, monkeypatch, tmp_path):
    metas = [
        PodMeta(name="ppl2-a", namespace="ns", deploy_name="ppl2"),
        PodMeta(name="web-0", namespace="ns", deploy_name="web"),
    ]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        page.deploy_combo.setCurrentText("ppl2")
        assert page._selected_pods() == ["ppl2-a"]

        # 回到「全部」：「全部 Pod」模式恢复整个命名空间范围
        page.deploy_combo.setCurrentText("全部")
        page.all_radio.setChecked(True)
        assert set(page._selected_pods()) == {"ppl2-a", "web-0"}
    finally:
        page.deleteLater()


def test_default_manual_mode_nothing_checked(app, monkeypatch, tmp_path):
    """默认手动勾选、全部不勾选：直接采集提示无选中。"""
    metas = [PodMeta(name="ppl2-a", namespace="ns", deploy_name="ppl2"),
             PodMeta(name="web-0", namespace="ns", deploy_name="web")]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        assert page.pick_radio.isChecked()
        assert not page.all_radio.isChecked()
        assert page._selected_pods() == []
    finally:
        page.deleteLater()


def test_select_all_and_deselect_all(app, monkeypatch, tmp_path):
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


def test_select_all_respects_search_filter(app, monkeypatch, tmp_path):
    """搜索框在已选/可见基础上过滤：全选只勾当前过滤结果。"""
    metas = [PodMeta(name="ppl2-a", namespace="ns", deploy_name="ppl2"),
             PodMeta(name="web-0", namespace="ns", deploy_name="web")]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        page.search_edit.setText("web")
        page._on_select_all()
        assert page._selected_pods() == ["web-0"]
    finally:
        page.deleteLater()


def test_deploy_combo_min_width(app, monkeypatch, tmp_path):
    page = _build_page(app, monkeypatch, tmp_path, [])
    try:
        assert page.deploy_combo.minimumWidth() >= 240
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
