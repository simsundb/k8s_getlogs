import html as _html
import json
from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QTextEdit,
                               QVBoxLayout, QWidget)

from ..k8s_client import get_pods_meta
from ..models import PodMeta
from .chart_dialog import ChartDialog
from .host_ns_selector import HostNamespaceSelector
from .icons import set_icon

FILTER_FIELDS = ["deployName", "project", "namespace", "node", "image",
                 "pipelineName", "uuid", "podIP", "src", "status", "pod"]


def _field_value(pm: PodMeta, field: str) -> str:
    """从 PodMeta 各来源取字段值：显式映射 → labels → annotations → 特殊字段。"""
    mapping = {
        "deployName": pm.deploy_name,
        "pod": pm.name,
        "namespace": pm.namespace,
        "node": pm.node,
        "podIP": pm.pod_ip,
        "status": pm.status,
    }
    if field in mapping:
        return mapping[field]
    if field in pm.labels:
        return pm.labels[field]
    if field in pm.annotations:
        return pm.annotations[field]
    if field == "uuid":
        return pm.annotations.get("uuid", "")
    if field == "image":
        containers = pm.full_json.get("spec", {}).get("containers", [])
        return containers[0].get("image", "") if containers else ""
    return ""


def _searchable_text(pm: PodMeta) -> str:
    """拼接全部可检索字段值（含标签/注解值），供关键字全字段包含匹配。"""
    parts = [_field_value(pm, f) for f in FILTER_FIELDS]
    parts.extend(pm.labels.values())
    parts.extend(pm.annotations.values())
    return " ".join(parts).lower()


def _describe_meta(pm: PodMeta) -> str:
    """生成明细对话框的中文字段说明：关键字段 + 值 + 简短提示。"""
    s = pm.summary()
    full = pm.full_json
    spec = full.get("spec", {})
    containers = spec.get("containers", [])
    image = containers[0].get("image", "") if containers else ""
    status = pm.status or full.get("status", {}).get("phase", "(未知)")
    env_names = []
    for c in containers:
        for e in c.get("env", []):
            if e.get("name"):
                env_names.append(e["name"])
    labels = pm.labels or full.get("metadata", {}).get("labels", {})
    annotations = pm.annotations or full.get("metadata", {}).get("annotations", {})
    lines = [
        f"名称       ：{pm.name}",
        f"命名空间   ：{pm.namespace}",
        f"所属部署名 ：{pm.deploy_name}   （注解 deployName，用于按部署分组抓取日志）",
        f"所在节点   ：{pm.node or '(未知)'}",
        f"Pod IP    ：{pm.pod_ip or '(未分配)'}",
        f"启动时间   ：{s['startTime'] or '(未知)'}",
        f"重启次数   ：{s['restartCount']}   （0 = 从未重启；>0 且持续增长通常为崩溃循环）",
        f"运行状态   ：{status}",
        f"镜像       ：{image or '(未知)'}",
    ]
    if env_names:
        lines.append(f"环境变量   ：{', '.join(env_names)}")
    lines.append(f"标签       ：{len(labels)} 项键值对（见下方完整 JSON）")
    lines.append(f"注解       ：{len(annotations)} 项（含 uuid、deployName 等平台元数据）")
    return "\n".join(lines)


def export_table_html(headers: list[str], rows: list[list[str]], path) -> str:
    """把查询结果表格导出为独立 HTML（UTF-8，带样式），返回文件路径。"""
    thead = "".join(f"<th>{_html.escape(str(h))}</th>" for h in headers)
    trows = ["<tr>" + "".join(f"<td>{_html.escape(str(v))}</td>" for v in row)
             + "</tr>" for row in rows]
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>查询统计结果</title>
<style>
  body {{ font-family:"Microsoft YaHei","PingFang SC",sans-serif; background:#f3f5f9; margin:20px; color:#2b3240; }}
  h1 {{ font-size:20px; }}
  .summary {{ color:#6a7380; margin-bottom:14px; }}
  table {{ border-collapse:collapse; width:100%; background:#fff; }}
  th,td {{ border:1px solid #d8dce4; padding:6px 10px; font-size:13px; text-align:left; }}
  th {{ background:#3b6fc4; color:#fff; }}
  tr:nth-child(even) {{ background:#f5f7fb; }}
</style>
</head>
<body>
  <h1>查询统计结果</h1>
  <div class="summary">共 {len(rows)} 行</div>
  <table><thead><tr>{thead}</tr></thead><tbody>{''.join(trows)}</tbody></table>
</body>
</html>
"""
    path = str(path)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path


class AnalyzePage(QWidget):
    def __init__(self, hosts_provider, parent=None):
        super().__init__(parent)
        self.metas = []

        root = QVBoxLayout(self)
        self.selector = HostNamespaceSelector(hosts_provider, self)
        root.addWidget(self.selector)

        # 条件过滤：固定 2 个条件行（字段/操作/值），多条件 AND
        cond_group = QGroupBox("条件过滤（多条件 AND）")
        cond_layout = QVBoxLayout(cond_group)
        self.cond_rows = []
        for _ in range(2):
            row = QHBoxLayout()
            field = QComboBox()
            field.addItems(FILTER_FIELDS)
            field.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            op = QComboBox()
            op.addItems(["等于", "包含"])
            op.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            value = QLineEdit()
            row.addWidget(field)
            row.addWidget(op)
            row.addWidget(value, 1)
            cond_layout.addLayout(row)
            self.cond_rows.append((field, op, value))
        btn_row = QHBoxLayout()
        self.query_btn = QPushButton("查询")
        self.query_btn.setProperty("primary", True)
        set_icon(self.query_btn, "search", color="white")
        self.query_btn.setToolTip("按上方条件过滤查询 Pod")
        self.clear_btn = QPushButton("清空条件")
        set_icon(self.clear_btn, "filter")
        self.clear_btn.setToolTip("清空全部过滤与搜索条件")
        btn_row.addWidget(self.query_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch(1)
        cond_layout.addLayout(btn_row)
        root.addWidget(cond_group)

        # 分组统计（文本结果；图形已按需求移除，表格获得更大展示区）
        grp_row = QHBoxLayout()
        grp_row.addWidget(QLabel("分组字段:"))
        self.group_combo = QComboBox()
        self.group_combo.addItems(["node", "project", "deployName", "image", "status"])
        self.group_combo.setMinimumWidth(140)
        self.group_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        grp_row.addWidget(self.group_combo)
        self.group_btn = QPushButton("统计")
        self.group_btn.setProperty("primary", True)
        set_icon(self.group_btn, "bar-chart-2", color="white")
        self.group_btn.setToolTip("按所选字段统计 Pod 分布")
        grp_row.addWidget(self.group_btn)
        grp_row.addWidget(QLabel("结果:"))
        self.group_result = QLabel("")
        grp_row.addWidget(self.group_result, 1)
        root.addLayout(grp_row)

        # 关键字搜索 + 导出
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("关键字搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "全字段包含匹配：部署名/Pod/IP/镜像/项目/节点/状态/标签/注解...")
        self.search_edit.setMinimumWidth(240)
        search_row.addWidget(self.search_edit, 1)
        self.search_btn = QPushButton("搜索")
        set_icon(self.search_btn, "search")
        self.search_btn.setToolTip("全字段包含匹配当前关键字")
        search_row.addWidget(self.search_btn)
        self.export_html_btn = QPushButton("导出 HTML")
        set_icon(self.export_html_btn, "file-text")
        self.export_html_btn.setToolTip("把当前查询结果导出为独立 HTML 文件")
        search_row.addWidget(self.export_html_btn)
        root.addLayout(search_row)

        # 结果表格（Pod 明细）：占据剩余高度，是页面上最大的框
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["deployName", "pod", "project", "node", "image", "podIP", "restartCount", "startTime"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setWordWrap(False)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setMinimumHeight(260)          # Pod 明细区尽量大
        self.table.itemDoubleClicked.connect(self._show_detail)
        root.addWidget(self.table, 1)

        self.selector.ns_combo.currentIndexChanged.connect(lambda _i: self._load_pods())
        self.selector.connectionFailed.connect(self._on_connection_failed)
        self.query_btn.clicked.connect(self._apply_query)
        self.clear_btn.clicked.connect(self._clear_conditions)
        self.group_btn.clicked.connect(self._group_stats)
        self.search_btn.clicked.connect(self._apply_query)
        self.export_html_btn.clicked.connect(self._export_html)

    def _load_pods(self):
        ns = self.selector.ns_combo.currentText()
        if not ns:
            return
        try:
            self.metas = get_pods_meta(self.selector.client(), ns)
        except Exception as e:
            self._clear_data()
            self.group_result.setText(f"加载 Pod 失败: {e}")
            return
        self._apply_query()

    def _clear_data(self):
        """数据源失效时清空缓存与界面，避免查询/统计操作到旧数据。"""
        self.metas = []
        self.table.setRowCount(0)
        self.group_result.setText("")

    def _on_connection_failed(self, _message):
        self._clear_data()

    def _clear_conditions(self):
        for _, _, value in self.cond_rows:
            value.clear()
        self.search_edit.clear()

    def _apply_query(self):
        if not self.metas:
            return
        metas = list(self.metas)
        for field, op, value in self.cond_rows:
            text = value.text().strip()
            if not text:
                continue
            metas = [pm for pm in metas
                     if self._match(pm, field.currentText(), op.currentText(), text)]
        kw = self.search_edit.text().strip().lower()
        if kw:
            metas = [pm for pm in metas if kw in _searchable_text(pm)]
        self._fill_table(metas)

    def _match(self, pm, field, op, text):
        val = _field_value(pm, field)
        return val == text if op == "等于" else text.lower() in val.lower()

    def _fill_table(self, metas):
        self.table.setRowCount(0)
        for i, pm in enumerate(metas):
            s = pm.summary()
            values = [s["deployName"], s["pod"], s["project"], s["node"], s["image"],
                      s["podIP"], str(s["restartCount"]), s["startTime"]]
            self.table.insertRow(i)
            for j, v in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(v))
            self.table.item(i, 0).setData(Qt.UserRole, pm)

    def _group_stats(self):
        if not self.metas:
            return
        field = self.group_combo.currentText()
        counter = Counter(_field_value(pm, field) or "(空)" for pm in self.metas)
        # 数据多时若把统计结果拼成文本塞进页面 QLabel 会把界面撑得很大，
        # 改为弹出图表对话框展示，主界面保持紧凑
        ChartDialog.show_stats(counter, field, self.metas, self)

    def _export_html(self):
        if self.table.rowCount() == 0:
            self.group_result.setText("没有可导出的结果")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 HTML", "query_result.html", "HTML 文件 (*.html)")
        if not path:
            return
        headers = [self.table.horizontalHeaderItem(c).text()
                   for c in range(self.table.columnCount())]
        rows = [[self.table.item(r, c).text() if self.table.item(r, c) else ""
                 for c in range(self.table.columnCount())]
                for r in range(self.table.rowCount())]
        try:
            export_table_html(headers, rows, path)
        except Exception as e:
            self.group_result.setText(f"导出 HTML 失败: {e}")
            return
        self.group_result.setText(f"已导出 {len(rows)} 行 → {path}")

    def _show_detail(self, item):
        pm = item.data(Qt.UserRole)
        if not pm:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Pod 明细：{pm.name}")
        dlg.resize(780, 640)
        lay = QVBoxLayout(dlg)

        tip = QLabel("关键元数据说明见上方；完整原始 JSON 在下方只读区。")
        tip.setStyleSheet("color: #6a7380;")
        lay.addWidget(tip)

        desc = QTextEdit()
        desc.setReadOnly(True)
        desc.setPlainText(_describe_meta(pm))

        raw = QPlainTextEdit()
        raw.setReadOnly(True)
        raw.setPlainText(json.dumps(pm.full_json, ensure_ascii=False, indent=2))

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(desc)
        splitter.addWidget(raw)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 400])
        lay.addWidget(splitter, 1)

        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(dlg.reject)
        lay.addWidget(box)
        dlg.exec()
