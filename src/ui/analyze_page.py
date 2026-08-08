import json
from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QDialogButtonBox, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

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
        grp_row.addWidget(self.group_combo)
        self.group_btn = QPushButton("统计")
        grp_row.addWidget(self.group_btn)
        grp_row.addWidget(QLabel("结果:"))
        self.group_result = QLabel("")
        grp_row.addWidget(self.group_result, 1)
        root.addLayout(grp_row)

        # 关键字搜索
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("关键字搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("匹配 deployName/image/node/project/pod...")
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
        self.table.itemDoubleClicked.connect(self._show_detail)
        root.addWidget(self.table, 1)

        self.selector.namespacesLoaded.connect(lambda _n: self._load_pods())
        self.selector.connectionFailed.connect(lambda _m: self.table.setRowCount(0))
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
            self.table.setRowCount(0)
            self.group_result.setText(f"加载 Pod 失败: {e}")
            return
        self._apply_query()

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
            metas = [pm for pm in metas
                     if any(kw in _field_value(pm, f).lower()
                            for f in ["deployName", "image", "node", "project", "pod"])]
        self._fill_table(metas)

    def _match(self, pm, field, op, text):
        val = _field_value(pm, field)
        return val == text if op == "等于" else text.lower() in val.lower()

    def _fill_table(self, metas):
        self.table.setRowCount(0)
        for i, pm in enumerate(metas):
            s = pm.summary()
            values = [s["deployName"], pm.name, s["project"], s["node"], s["image"],
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

    def _show_detail(self, item):
        pm = item.data(Qt.UserRole)
        if not pm:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(pm.name)
        lay = QVBoxLayout(dlg)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(json.dumps(pm.full_json, ensure_ascii=False, indent=2))
        lay.addWidget(text)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(dlg.reject)
        lay.addWidget(box)
        dlg.resize(720, 560)
        dlg.exec()
