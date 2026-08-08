import json
from collections import Counter

from PySide6.QtCharts import (QBarCategoryAxis, QBarSet, QChart, QChartView,
                              QHorizontalBarSeries, QValueAxis)
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QDialogButtonBox, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextEdit, QVBoxLayout,
                               QWidget)

from ..k8s_client import get_pods_meta
from ..models import PodMeta
from .host_ns_selector import HostNamespaceSelector

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


class AnalyzePage(QWidget):
    def __init__(self, hosts_provider, parent=None):
        super().__init__(parent)
        self.metas = []

        root = QVBoxLayout(self)
        self.selector = HostNamespaceSelector(hosts_provider, self)
        root.addWidget(self.selector)

        # 条件过滤：固定 3 个条件行（字段/操作/值），够用且简单
        cond_group = QGroupBox("条件过滤（多条件 AND）")
        cond_layout = QVBoxLayout(cond_group)
        self.cond_rows = []
        for _ in range(3):
            row = QHBoxLayout()
            field = QComboBox()
            field.addItems(FILTER_FIELDS)
            op = QComboBox()
            op.addItems(["等于", "包含"])
            value = QLineEdit()
            row.addWidget(field)
            row.addWidget(op)
            row.addWidget(value, 1)
            cond_layout.addLayout(row)
            self.cond_rows.append((field, op, value))
        btn_row = QHBoxLayout()
        self.query_btn = QPushButton("查询")
        self.query_btn.setProperty("primary", True)
        self.clear_btn = QPushButton("清空条件")
        btn_row.addWidget(self.query_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch(1)
        cond_layout.addLayout(btn_row)
        root.addWidget(cond_group)

        # 分组统计
        grp_row = QHBoxLayout()
        grp_row.addWidget(QLabel("分组字段:"))
        self.group_combo = QComboBox()
        self.group_combo.addItems(["node", "project", "deployName", "image", "status"])
        self.group_combo.setMinimumWidth(140)
        grp_row.addWidget(self.group_combo)
        self.group_btn = QPushButton("统计")
        self.group_btn.setProperty("primary", True)
        grp_row.addWidget(self.group_btn)
        grp_row.addWidget(QLabel("结果:"))
        self.group_result = QLabel("")
        grp_row.addWidget(self.group_result, 1)
        root.addLayout(grp_row)

        # 分组统计图形（QtCharts 横向条形图，点「统计」后展示）
        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setMinimumHeight(200)
        self.chart_view.setVisible(False)
        root.addWidget(self.chart_view)

        # 关键字搜索
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("关键字搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "全字段包含匹配：部署名/Pod/IP/镜像/项目/节点/状态/标签/注解...")
        self.search_edit.setMinimumWidth(240)
        search_row.addWidget(self.search_edit, 1)
        self.search_btn = QPushButton("搜索")
        search_row.addWidget(self.search_btn)
        root.addLayout(search_row)

        # 结果表格
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["deployName", "pod", "project", "node", "image", "podIP", "restartCount", "startTime"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # 单元格内容超宽时不折行、自动出横向滚动条；行数超出时纵向滚动条自动出现
        self.table.setWordWrap(False)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.itemDoubleClicked.connect(self._show_detail)
        root.addWidget(self.table, 1)

        # 命名空间下拉切换/加载时重载 Pod 元数据（与采集页一致，避免表格停留在旧命名空间）
        self.selector.ns_combo.currentIndexChanged.connect(lambda _i: self._load_pods())
        self.selector.connectionFailed.connect(self._on_connection_failed)
        self.query_btn.clicked.connect(self._apply_query)
        self.clear_btn.clicked.connect(self._clear_conditions)
        self.group_btn.clicked.connect(self._group_stats)
        self.search_btn.clicked.connect(self._apply_query)

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
        self.chart_view.setChart(None)
        self.chart_view.setVisible(False)

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
        top = counter.most_common(8)
        self.group_result.setText("  ".join(f"{k}: {n}" for k, n in top))
        self._render_group_chart(top, field)

    def _render_group_chart(self, counts, field):
        """把分组计数画成横向条形图；counts 为空时隐藏图表区。"""
        if not counts:
            self.chart_view.setChart(None)
            self.chart_view.setVisible(False)
            return
        series = QHorizontalBarSeries()
        barset = QBarSet("数量")
        barset.setColor(QColor("#3b6fc4"))
        for _name, n in counts:
            barset.append(n)
        series.append(barset)

        chart = QChart()
        chart.setTitle(f"{field} 分组分布（Top {len(counts)}）")
        chart.addSeries(series)

        axis_y = QBarCategoryAxis()
        axis_y.append([name for name, _n in counts])
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        axis_x = QValueAxis()
        axis_x.setLabelFormat("%d")
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        chart.legend().setVisible(False)
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        chart.setBackgroundBrush(QBrush(QColor("#ffffff")))
        self.chart_view.setChart(chart)
        self.chart_view.setVisible(True)

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
