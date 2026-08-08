# tests/test_analyze_chart.py
"""③ 页分组统计图形 + 关键字全字段模糊查询（QApplication offscreen 构建页面）。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCharts import QHorizontalBarSeries
from PySide6.QtWidgets import QApplication

from src.models import PodMeta


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


def test_group_stats_renders_bar_chart(app, monkeypatch, tmp_path):
    metas = [
        PodMeta(name=f"p{i}", namespace="ns", deploy_name=f"d{i % 2}",
                node=f"node-{i % 2}")
        for i in range(6)
    ]
    page = _build_page(app, monkeypatch, tmp_path, metas)
    try:
        page.group_combo.setCurrentText("deployName")
        page._group_stats()
        # setVisible(True) 后不再处于显式隐藏态（父窗口未 show，故用 isHidden 判定）
        assert not page.chart_view.isHidden()
        chart = page.chart_view.chart()
        assert chart is not None
        assert isinstance(chart.series()[0], QHorizontalBarSeries)
        assert chart.series()[0].barSets()[0].count() == 2  # d0、d1 两组
    finally:
        page.deleteLater()


def test_group_stats_empty_keeps_chart_hidden(app, monkeypatch, tmp_path):
    page = _build_page(app, monkeypatch, tmp_path, [])
    try:
        page._group_stats()
        assert page.chart_view.isHidden()
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
