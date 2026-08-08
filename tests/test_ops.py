# tests/test_ops.py
"""第④页 SSH 运维：预置命令、命令构建、表格解析、HTML/Excel 导出。"""
from openpyxl import load_workbook

from src.ops import (OPS_COMMANDS, OpsResult, build_command, export_excel,
                     export_html, parse_table_output)


# ---------- 预置命令 ----------
def test_ops_commands_well_formed():
    labels = [c.label for c in OPS_COMMANDS]
    assert len(labels) == len(set(labels))            # 名称唯一
    cats = {c.category for c in OPS_COMMANDS}
    assert cats <= {"集群", "节点", "应用", "存储"}
    assert len(OPS_COMMANDS) >= 15                     # 常规运维项数量足够
    for c in OPS_COMMANDS:
        assert c.command, c.label
        if "{namespace}" in c.command:
            assert c.needs_namespace, c.label         # 用命名空间的命令必须标记


def test_build_command_replaces_namespace():
    cmd = build_command("kubectl get pods -n {namespace} -o wide", "ns-1")
    assert cmd == "kubectl get pods -n ns-1 -o wide"


def test_build_command_without_placeholder_unchanged():
    cmd = build_command("kubectl cluster-info", "ns-1")
    assert cmd == "kubectl cluster-info"


def test_build_command_empty_namespace_uses_default():
    cmd = build_command("kubectl get pods -n {namespace}", "")
    assert cmd == "kubectl get pods -n default"


# ---------- 表格解析 ----------
def test_parse_table_output_aligned_columns():
    text = "NAME    STATUS   ROLES\nnode-1  Ready    master\nnode-2  Ready    worker\n"
    rows = parse_table_output(text)
    assert rows == [
        ["NAME", "STATUS", "ROLES"],
        ["node-1", "Ready", "master"],
        ["node-2", "Ready", "worker"],
    ]


def test_parse_table_output_single_word_line_kept_whole():
    text = "hello\nthis is a single spaced line\n"
    rows = parse_table_output(text)
    assert rows == [["hello"], ["this is a single spaced line"]]


def test_parse_table_output_ignores_blank_lines():
    assert parse_table_output("a  b\n\n\nc  d\n") == [["a", "b"], ["c", "d"]]


# ---------- HTML 导出 ----------
def _sample_results():
    return [
        OpsResult(label="节点列表", command="kubectl get nodes",
                  start_time="2026-08-08 10:00:00", ok=True,
                  output="NAME     STATUS\nnode-1    Ready", exit_code=0, duration=1.2),
        OpsResult(label="集群信息", command="kubectl cluster-info",
                  start_time="2026-08-08 10:00:05", ok=False,
                  error="error: no context", exit_code=1, duration=0.8),
    ]


def test_export_html_writes_utf8_file(tmp_path):
    out = tmp_path / "report.html"
    path = export_html(_sample_results(), out)
    assert path == str(out)
    text = out.read_text(encoding="utf-8")
    assert "SSH 运维结果" in text
    assert "节点列表" in text and "kubectl get nodes" in text
    assert "node-1" in text
    assert "失败" in text and "error: no context" in text
    assert 'charset="utf-8"' in text


# ---------- Excel 导出 ----------
def test_export_excel_writes_summary_and_per_result_sheets(tmp_path):
    out = tmp_path / "report.xlsx"
    export_excel(_sample_results(), out)
    assert out.exists()

    wb = load_workbook(out)
    assert wb.sheetnames == ["汇总", "1-节点列表", "2-集群信息"]

    ws = wb["汇总"]
    header = [c.value for c in ws[1]]
    assert header == ["序号", "运维项", "状态", "退出码", "耗时(秒)", "输出行数", "命令"]
    assert [c.value for c in ws[2]] == [1, "节点列表", "成功", 0, 1.2, 2,
                                        "kubectl get nodes"]

    detail = wb["1-节点列表"]
    assert detail["A1"].value == "运维项"
    assert detail["B1"].value == "节点列表"
    # 解析出的表头行落在明细工作表中
    assert detail["A9"].value == "NAME"
    assert detail["B9"].value == "STATUS"
    assert detail["A10"].value == "node-1"
