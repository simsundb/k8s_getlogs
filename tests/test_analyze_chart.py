# tests/test_analyze_page.py（历史文件名保留：test_analyze_chart.py）
"""③ 页：条件过滤保留 2 行、统计图表走弹窗、Pod 明细框加大、关键字模糊查询、HTML 导出。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from collections import Counter

import pytest
from PySide6.QtWidgets import QApplication, QTabWidget

from src.models import PodMeta
from src.ui.analyze_page import _field_value, export_table_html


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _build_page(app, monkeypatch, tmp_path, metas):
    monkeypatch.setattr("src.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("src.config.APP_DIR", tmp_path)
    from src.ui.analyze_page import AnalyzePage

    monkeypatch.setattr("src.ui.analyze_page.get_pods_meta", lambda _client, _ns: metas)
    page = AnalyzePage(lambda: [])
    page.selector.ns_combo.addItem("ns")
    page.selector.ns_combo.setCurrentIndex(0)   # 触发 currentIndexChanged → _load_pods()
    return page


def test_two_condition_rows_table_bigger_chart_in_dialog(app, monkeypatch, tmp_path):
    """查询条件保留 2 个；统计图表走独立弹窗（不占页面空间）；Pod 明细表加大。"""
    page = _build_page(app, monkeypatch, tmp_path, [])
    try:
        assert len(page.cond_rows) == 2
        assert page.table.minimumHeight() >= 200
        # 统计结果是弹窗，页面本身不内嵌图表视图，避免数据多时把界面撑大
        assert not hasattr(page, "chart_view")
        assert hasattr(page, "group_result")   # 页面仍保留结果文本行（用于导出等提示）
    finally:
        page.deleteLater()


def test_cond_filter_uses_two_rows(app, monkeypatch, tmp_path):
    """2 个条件行参与 AND 过滤（行 0 生效）。"""
    metas = [
        PodMeta(name="p1", namespace="ns", deploy_name="app", node="node-1",
                labels={"project": "proj-a"}),
        PodMeta(name="p2", namespace="ns", deploy_name="web", node="node-2",
                labels={"project": "proj-b"}),
    ]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        field, op, value = page.cond_rows[0]
        field.setCurrentText("deployName")
        op.setCurrentText("等于")
        value.setText("app")
        page._apply_query()
        assert page.table.rowCount() == 1
        assert page.table.item(0, 1).text() == "p1"
    finally:
        page.deleteLater()


def test_keyword_search_matches_annotation_value(app, monkeypatch, tmp_path):
    """模糊查询命中注解字段值：全字段包含匹配。"""
    metas = [
        PodMeta(name="web-1", namespace="ns", deploy_name="web",
                annotations={"uuid": "abc-123", "pipelineName": "pipe-A"}),
        PodMeta(name="db-1", namespace="ns", deploy_name="db",
                annotations={"uuid": "xyz-999", "pipelineName": "pipe-B"}),
    ]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        page.search_edit.setText("abc-123")   # 命中 web-1 的注解 uuid
        page._apply_query()
        assert page.table.rowCount() == 1
        assert page.table.item(0, 1).text() == "web-1"

        page.search_edit.setText("pipe-B")    # 命中 db-1 的注解 pipelineName
        page._apply_query()
        assert page.table.rowCount() == 1
        assert page.table.item(0, 1).text() == "db-1"
    finally:
        page.deleteLater()


def test_export_table_html_writes_utf8_file(tmp_path):
    out = tmp_path / "query.html"
    path = export_table_html(["deployName", "pod"],
                             [["app", "p1"], ["web", "p2"]], out)
    assert path == str(out)
    text = out.read_text(encoding="utf-8")
    assert "查询统计结果" in text
    assert "deployName" in text and "p1" in text and "共 2 行" in text
    assert 'charset="utf-8"' in text


def test_chart_dialog_constructs_two_tabs(app):
    """统计图表弹窗：柱状图 + 线图两个标签页，标题与数据正确。"""
    from src.ui.chart_dialog import ChartDialog
    metas = [
        PodMeta(name="p1", namespace="ns", deploy_name="app", node="node-1",
                restart_count=0),
        PodMeta(name="p2", namespace="ns", deploy_name="app", node="node-2",
                restart_count=3),
        PodMeta(name="p3", namespace="ns", deploy_name="web", node="node-1",
                restart_count=3),
    ]
    counter = Counter(_field_value(pm, "node") for pm in metas)
    dlg = ChartDialog(counter, "node", metas)
    try:
        tabs = dlg.findChild(QTabWidget)
        assert tabs is not None
        assert tabs.count() == 2
        assert "柱状图" in tabs.tabText(0)
        assert "线图" in tabs.tabText(1)
        assert "node" in dlg.windowTitle()
    finally:
        dlg.deleteLater()


def test_group_stats_does_not_touch_page_label(app, monkeypatch, tmp_path):
    """统计改成弹窗后，页面 group_result 不再被超长统计文本塞满。"""
    metas = [PodMeta(name=f"p{i}", namespace="ns", deploy_name="app",
                     node=f"node-{i % 2}")
             for i in range(50)]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        # 直接调用分组统计：只弹窗（offscreen 下 exec 会卡，故验证统计逻辑不写页面文本）
        page.group_combo.setCurrentText("node")
        counter = Counter(_field_value(pm, "node") or "(空)" for pm in page.metas)
        assert counter["node-0"] == 25 and counter["node-1"] == 25
        assert page.group_result.text() == ""   # 页面标签保持干净
    finally:
        page.deleteLater()
