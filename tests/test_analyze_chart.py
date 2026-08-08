# tests/test_analyze_page.py（历史文件名保留：test_analyze_chart.py）
"""③ 页：条件过滤保留 2 行、无图表、Pod 明细框加大、关键字模糊查询、HTML 导出。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src.models import PodMeta
from src.ui.analyze_page import export_table_html


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


def test_two_condition_rows_table_bigger_no_chart(app, monkeypatch, tmp_path):
    """查询条件保留 2 个；图表已移除；Pod 明细表加大。"""
    page = _build_page(app, monkeypatch, tmp_path, [])
    try:
        assert len(page.cond_rows) == 2
        assert not hasattr(page, "chart_view")
        assert page.table.minimumHeight() >= 200
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
