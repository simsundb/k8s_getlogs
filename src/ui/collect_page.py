# src/ui/collect_page.py
import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QStandardItem,
                           QStandardItemModel)
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from ..collector import Collector, write_manifest, zip_output
from ..config import load_config, save_config
from ..k8s_client import PATTERN_MAP, build_log_pattern, get_pods_meta
from ..models import DEFAULT_LOG_DIR, CollectSummary, CollectTask, human_size
from ..ssh_client import SSHClient
from .host_ns_selector import HostNamespaceSelector
from .log_panel import LogPanel
from .style import SELECT_BG


class CheckableCombo(QComboBox):
    """支持勾选多值的下拉框：点击项切换勾选，弹层保持打开方便连续多选。

    勾选结果通过 itemsToggled 通知；勾选某个部署名即选中该部署名下全部 Pod。
    """

    itemsToggled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self._model.itemChanged.connect(lambda _i: self.itemsToggled.emit())
        self.view().pressed.connect(self._on_pressed)
        self._keep_open = False

    def add_checkable_item(self, text, user_data=None):
        self.addItem(text)
        item = self._model.item(self.count() - 1)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Unchecked)          # 默认全部不勾选
        if user_data is not None:
            item.setData(user_data, Qt.UserRole)

    def checked_items(self) -> list[str]:
        return [self._model.item(r).text()
                for r in range(self._model.rowCount())
                if self._model.item(r).checkState() == Qt.Checked]

    def _on_pressed(self, index):
        item = self._model.itemFromIndex(index)
        if item is None or not (item.flags() & Qt.ItemIsUserCheckable):
            return
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked
                           else Qt.Checked)
        self._keep_open = True                    # 本次点击不收起弹层

    def hidePopup(self):
        if self._keep_open:
            self._keep_open = False
            return
        super().hidePopup()


class _CollectWorker(QThread):
    progress = Signal(object)                  # CollectResult
    finished_ok = Signal(object, object, object)  # (results, metas, summary)
    error = Signal(str)

    def __init__(self, tasks, metas, output_base, namespace, ssh_provider, parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self.metas = metas
        self.output_base = output_base
        self.namespace = namespace
        self.ssh_provider = ssh_provider
        self.cancel = Event()

    def cancel_request(self):
        self.cancel.set()

    def run(self):
        try:
            collector = Collector(self.ssh_provider, self.output_base, max_workers=4)
            results = collector.run(self.tasks, on_progress=self.progress.emit, cancel=self.cancel)
            summary = CollectSummary.build(results)
            self.finished_ok.emit(results, self.metas, summary)
        except Exception as e:
            self.error.emit(str(e))


class CollectPage(QWidget):
    def __init__(self, hosts_provider, parent=None):
        super().__init__(parent)
        self._worker = None
        self.metas = []
        cfg = load_config()

        root = QVBoxLayout(self)
        self.selector = HostNamespaceSelector(hosts_provider, self)
        root.addWidget(self.selector)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("存储目录:"))
        self.out_label = QLabel()
        out_row.addWidget(self.out_label, 1)
        self.choose_btn = QPushButton("选择存储目录")
        out_row.addWidget(self.choose_btn)
        root.addLayout(out_row)

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("日志目录:"))
        self.log_dir_edit = QLineEdit()
        self.log_dir_edit.setText(cfg.get("log_dir") or DEFAULT_LOG_DIR)
        self.log_dir_edit.setPlaceholderText("Pod 内日志目录，留空默认 /opt/logs")
        self.log_dir_edit.setMinimumWidth(220)
        src_row.addWidget(self.log_dir_edit)
        src_row.addSpacing(16)
        src_row.addWidget(QLabel("日志名:"))
        self.log_name_edit = QLineEdit()
        self.log_name_edit.setPlaceholderText("非空时匹配包含该名的 .log")
        self.log_name_edit.setMinimumWidth(180)
        src_row.addWidget(self.log_name_edit)
        src_row.addStretch(1)
        root.addLayout(src_row)

        pod_group = QGroupBox("Pod 选择")
        pod_layout = QVBoxLayout(pod_group)
        mode_row = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")        # 选择全部 Pod
        self.deselect_all_btn = QPushButton("取消全选")
        mode_row.addWidget(self.select_all_btn)
        mode_row.addWidget(self.deselect_all_btn)
        mode_row.addSpacing(16)
        mode_row.addWidget(QLabel("部署名(可多选):"))
        self.deploy_combo = CheckableCombo()             # 勾选部署名=选中其全部 Pod
        self.deploy_combo.setMinimumWidth(240)
        mode_row.addWidget(self.deploy_combo)
        mode_row.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("在已选基础上过滤：搜索 Pod 名 / 部署名...")
        self.search_edit.setMinimumWidth(220)
        mode_row.addWidget(self.search_edit)
        pod_layout.addLayout(mode_row)
        self.pod_list = QListWidget()
        self.pod_list.setSelectionMode(QListWidget.NoSelection)
        self.pod_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.pod_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        pod_layout.addWidget(self.pod_list, 1)
        root.addWidget(pod_group, 1)

        cat_row = QHBoxLayout()
        cat_row.addWidget(QLabel("日志类别:"))
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(list(PATTERN_MAP.keys()))
        self.cat_combo.setMinimumWidth(150)
        cat_row.addWidget(self.cat_combo)
        cat_row.addStretch(1)
        self.start_btn = QPushButton("开始采集")
        self.start_btn.setProperty("primary", True)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setEnabled(False)
        cat_row.addWidget(self.start_btn)
        cat_row.addWidget(self.cancel_btn)
        root.addLayout(cat_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log_panel = LogPanel()
        root.addWidget(self.log_panel, 1)

        self.selector.connectionFailed.connect(self._on_error)
        # 命名空间下拉切换时重载 Pod 列表（选中即加载）
        self.selector.ns_combo.currentIndexChanged.connect(lambda _i: self._load_pods())
        self.choose_btn.clicked.connect(self._choose_dir)
        self.start_btn.clicked.connect(self.start_collect)
        self.cancel_btn.clicked.connect(self._cancel)
        self.deploy_combo.itemsToggled.connect(self._on_deploy_toggled)
        self.search_edit.textChanged.connect(lambda _t: self._update_visibility())
        self.select_all_btn.clicked.connect(self._on_select_all)
        self.deselect_all_btn.clicked.connect(self._on_deselect_all)
        self.pod_list.itemChanged.connect(self._on_pod_item_changed)

        self.out_dir = Path(cfg.get("output_dir") or str(Path.cwd() / "output"))
        self._update_out_label()

    def _update_out_label(self):
        self.out_label.setText(str(self.out_dir))

    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择存储目录", str(self.out_dir))
        if d:
            self.out_dir = Path(d)
            data = load_config()
            data["output_dir"] = str(self.out_dir)
            save_config(data)
            self._update_out_label()

    def _load_pods(self):
        ns = self.selector.ns_combo.currentText()
        if not ns:
            return
        try:
            self.metas = get_pods_meta(self.selector.client(), ns)
        except Exception as e:
            self._on_error(f"加载 Pod 失败: {e}")
            return
        self.pod_list.clear()
        # 重建部署名多选下拉（全部默认不勾选）；blockSignals 避免重建过程触发勾选逻辑
        self.deploy_combo.blockSignals(True)
        self.deploy_combo.clear()
        for deploy in sorted({pm.deploy_name for pm in self.metas}):
            self.deploy_combo.add_checkable_item(deploy)
        self.deploy_combo.blockSignals(False)
        for pm in self.metas:
            item = QListWidgetItem(f"[{pm.deploy_name}]  {pm.name}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)   # 默认全部不勾选
            item.setData(Qt.UserRole, pm.name)
            item.setData(Qt.UserRole + 1, pm.deploy_name)   # 部署名，供按部署名勾选
            self.pod_list.addItem(item)
        self._update_visibility()
        self.log_panel.append_log(f"命名空间 {ns} 共加载 {len(self.metas)} 个 Pod")

    def _update_visibility(self):
        """搜索框只缩窄可见范围（隐藏不匹配行）；采集 = 已勾选 ∩ 可见。"""
        text = self.search_edit.text().strip().lower()
        for i in range(self.pod_list.count()):
            item = self.pod_list.item(i)
            item.setHidden(bool(text and text not in item.text().lower()))

    def _on_deploy_toggled(self):
        """部署名多选变化：勾选=选中该部署全部 Pod，取消=取消该部署全部 Pod。"""
        model = self.deploy_combo.model()
        for r in range(model.rowCount()):
            d_item = model.item(r)
            if not (d_item.flags() & Qt.ItemIsUserCheckable):
                continue
            target = d_item.checkState() == Qt.Checked
            for i in range(self.pod_list.count()):
                item = self.pod_list.item(i)
                if item.data(Qt.UserRole + 1) == d_item.text():
                    item.setCheckState(Qt.Checked if target else Qt.Unchecked)
        self._update_visibility()

    def _sync_deploy_combo(self):
        """让部署名勾选状态与 Pod 实际勾选同步：某部署全部勾选才显示勾选。"""
        by_deploy: dict[str, list[bool]] = {}
        for i in range(self.pod_list.count()):
            item = self.pod_list.item(i)
            by_deploy.setdefault(item.data(Qt.UserRole + 1), []).append(
                item.checkState() == Qt.Checked)
        self.deploy_combo.blockSignals(True)
        model = self.deploy_combo.model()
        for r in range(model.rowCount()):
            item = model.item(r)
            states = by_deploy.get(item.text())
            if states:
                item.setCheckState(Qt.Checked if all(states) else Qt.Unchecked)
        self.deploy_combo.blockSignals(False)

    def _on_select_all(self):
        """全选 = 选择全部 Pod（含被搜索过滤隐藏的；采集时仍按可见范围收窄）。"""
        for i in range(self.pod_list.count()):
            item = self.pod_list.item(i)
            if item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(Qt.Checked)
        self._sync_deploy_combo()

    def _on_deselect_all(self):
        for i in range(self.pod_list.count()):
            item = self.pod_list.item(i)
            if item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(Qt.Unchecked)
        self._sync_deploy_combo()

    def _on_pod_item_changed(self, item):
        """勾选/取消时切换条目背景色并同步部署名勾选状态。"""
        if item.checkState() == Qt.Checked:
            item.setBackground(QBrush(QColor(SELECT_BG)))
        else:
            item.setBackground(QBrush())
        self._sync_deploy_combo()

    def _selected_pods(self):
        """采集集 = 已勾选且当前可见的 Pod（过滤在已选基础上缩窄）。"""
        return [self.pod_list.item(i).data(Qt.UserRole)
                for i in range(self.pod_list.count())
                if not self.pod_list.item(i).isHidden()
                and self.pod_list.item(i).checkState() == Qt.Checked]

    def _source_settings(self) -> tuple[str, str]:
        """采集来源：日志目录（留空默认 /opt/logs）+ 远端 tar 通配符。"""
        log_dir = self.log_dir_edit.text().strip() or DEFAULT_LOG_DIR
        pattern = build_log_pattern(self.cat_combo.currentText(),
                                    self.log_name_edit.text().strip())
        return log_dir, pattern

    def _build_tasks(self, ns: str, pod_names: list[str]) -> list[CollectTask]:
        """按当前页面设置构建采集任务（类别/日志目录/日志名）。"""
        log_dir, pattern = self._source_settings()
        by_name = {pm.name: pm for pm in self.metas}
        return [CollectTask(pod_name=n, deploy_name=by_name[n].deploy_name,
                            namespace=ns, pattern=pattern, log_dir=log_dir)
                for n in pod_names]

    def start_collect(self):
        ns = self.selector.ns_combo.currentText()
        if not ns or not self.metas:
            self._on_error("请先选择命名空间并加载 Pod")
            return
        pod_names = self._selected_pods()
        if not pod_names:
            self._on_error("没有选中的 Pod")
            return
        host = self.selector.current_host()
        if host is None:
            self._on_error("未选择主机")
            return
        category = self.cat_combo.currentText()
        tasks = self._build_tasks(ns, pod_names)
        log_dir, _pattern = self._source_settings()
        # 记住日志目录设置，下次打开沿用（日志名属临时过滤，不持久化）
        data = load_config()
        if data.get("log_dir") != log_dir:
            data["log_dir"] = log_dir
            save_config(data)
        # 快照采集开始时刻的日期，应用跨午夜时避免落到昨天的目录
        self._date = datetime.datetime.now().strftime("%Y-%m-%d")
        date_dir = self.out_dir / self._date
        date_dir.mkdir(parents=True, exist_ok=True)
        self.progress.setRange(0, len(tasks))
        self.progress.setValue(0)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_panel.clear_log()
        name = self.log_name_edit.text().strip() or "全部"
        self.log_panel.append_log(
            f"开始采集：{len(tasks)} 个 Pod，类别={category}，"
            f"日志目录={log_dir}，日志名={name}，存储={self.out_dir}")

        # 快照主机/命名空间/类别，采集过程中用户切换界面选择不影响本批任务：
        # 工厂由线程池调用，绝不能跨线程访问 Qt 控件，故闭包只捕获 HostConfig 快照。
        self._ns = ns
        self._category = category

        def _factory():
            return SSHClient(host.ip, host.port, host.username, host.password).connect()

        self._worker = _CollectWorker(
            tasks, self.metas, self.out_dir / self._date, ns, _factory, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_progress(self, result):
        if result.ok:
            self.log_panel.append_log(
                f"  ✓ {result.pod_name}：{result.file_count} 个文件，"
                f"{human_size(result.total_bytes)}")
        else:
            self.log_panel.append_log(f"  - {result.pod_name}：{result.error}")
        self.progress.setValue(self.progress.value() + 1)

    def _on_finished(self, results, metas, summary):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        # 使用开始采集时的快照，避免采集期间用户切换命名空间/类别导致 manifest 与压缩包命名漂移
        ns = self._ns
        category = self._category
        manifest_path = self.out_dir / self._date / "pods_manifest.json"
        write_manifest(manifest_path, ns, metas, results)
        zip_path = zip_output(self.out_dir, self._date, ns, category)
        self.log_panel.append_log(
            f"汇总：共 {summary.total} 个 Pod，成功 {summary.ok}，"
            f"失败 {summary.failed}，跳过 {summary.skipped}，"
            f"日志总大小 {human_size(summary.total_bytes)}")
        self.log_panel.append_log(f"压缩包：{zip_path}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.out_dir)))
        self._worker = None

    def _cancel(self):
        if self._worker:
            self._worker.cancel_request()
            self.log_panel.append_log("取消请求已发送，正在停止...")

    def closeEvent(self, event):
        # 关闭窗口时停止仍在运行的采集线程，避免 "QThread: Destroyed while thread is still running"
        if self._worker and self._worker.isRunning():
            self._worker.cancel_request()
            self._worker.wait(3000)
        self._worker = None
        super().closeEvent(event)

    def _on_error(self, msg):
        self.log_panel.append_log(f"[错误] {msg}")

    def _on_worker_error(self, msg):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.log_panel.append_log(f"[错误] {msg}")
        self._worker = None
