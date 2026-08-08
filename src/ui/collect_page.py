# src/ui/collect_page.py
import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QProgressBar, QPushButton, QRadioButton,
                               QVBoxLayout, QWidget)

from ..collector import Collector, write_manifest, zip_output
from ..config import load_config, save_config
from ..k8s_client import PATTERN_MAP, get_pods_meta
from ..models import CollectSummary, CollectTask
from ..ssh_client import SSHClient
from .host_ns_selector import HostNamespaceSelector
from .log_panel import LogPanel


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
        self._date_name = datetime.datetime.now().strftime("%Y-%m-%d")

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

        pod_group = QGroupBox("Pod 选择")
        pod_layout = QVBoxLayout(pod_group)
        mode_row = QHBoxLayout()
        self.all_radio = QRadioButton("全部 Pod")
        self.pick_radio = QRadioButton("手动勾选")
        self.all_radio.setChecked(True)
        mode_row.addWidget(self.all_radio)
        mode_row.addWidget(self.pick_radio)
        mode_row.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索 Pod 名 / 部署名...")
        mode_row.addWidget(self.search_edit)
        pod_layout.addLayout(mode_row)
        self.pod_list = QListWidget()
        self.pod_list.setSelectionMode(QListWidget.NoSelection)
        pod_layout.addWidget(self.pod_list, 1)
        root.addWidget(pod_group, 1)

        cat_row = QHBoxLayout()
        cat_row.addWidget(QLabel("日志类别:"))
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(list(PATTERN_MAP.keys()))
        cat_row.addWidget(self.cat_combo)
        cat_row.addStretch(1)
        self.start_btn = QPushButton("开始采集")
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
        self.all_radio.toggled.connect(lambda _: self._update_pod_state())
        self.search_edit.textChanged.connect(self._filter_pods)

        cfg = load_config()
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
        for pm in self.metas:
            item = QListWidgetItem(f"[{pm.deploy_name}]  {pm.name}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, pm.name)
            self.pod_list.addItem(item)
        self.log_panel.append_log(f"命名空间 {ns} 共加载 {len(self.metas)} 个 Pod")

    def _filter_pods(self, text):
        text = text.strip().lower()
        for i in range(self.pod_list.count()):
            item = self.pod_list.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())

    def _update_pod_state(self):
        pick = self.pick_radio.isChecked()
        for i in range(self.pod_list.count()):
            item = self.pod_list.item(i)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable if pick
                          else item.flags() & ~Qt.ItemIsUserCheckable)

    def _selected_pods(self):
        if self.all_radio.isChecked():
            return [pm.name for pm in self.metas]
        return [self.pod_list.item(i).data(Qt.UserRole)
                for i in range(self.pod_list.count())
                if not self.pod_list.item(i).isHidden()
                and self.pod_list.item(i).checkState() == Qt.Checked]

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
        pattern = PATTERN_MAP[category]
        by_name = {pm.name: pm for pm in self.metas}
        tasks = [CollectTask(pod_name=n, deploy_name=by_name[n].deploy_name,
                             namespace=ns, pattern=pattern) for n in pod_names]
        date_dir = self.out_dir / self._date_name
        date_dir.mkdir(parents=True, exist_ok=True)
        self.progress.setRange(0, len(tasks))
        self.progress.setValue(0)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_panel.clear_log()
        self.log_panel.append_log(
            f"开始采集：{len(tasks)} 个 Pod，类别={category}，存储={self.out_dir}")

        # 快照主机/命名空间/类别，采集过程中用户切换界面选择不影响本批任务：
        # 工厂由线程池调用，绝不能跨线程访问 Qt 控件，故闭包只捕获 HostConfig 快照。
        self._ns = ns
        self._category = category

        def _factory():
            return SSHClient(host.ip, host.port, host.username, host.password).connect()

        self._worker = _CollectWorker(
            tasks, self.metas, self.out_dir / self._date_name, ns, _factory, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_progress(self, result):
        if result.ok:
            self.log_panel.append_log(f"  ✓ {result.pod_name}：{result.file_count} 个文件")
        else:
            self.log_panel.append_log(f"  - {result.pod_name}：{result.error}")
        self.progress.setValue(self.progress.value() + 1)

    def _on_finished(self, results, metas, summary):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        # 使用开始采集时的快照，避免采集期间用户切换命名空间/类别导致 manifest 与压缩包命名漂移
        ns = self._ns
        category = self._category
        manifest_path = self.out_dir / self._date_name / "pods_manifest.json"
        write_manifest(manifest_path, ns, metas, results)
        zip_path = zip_output(self.out_dir, self._date_name, ns, category)
        self.log_panel.append_log(
            f"完成：成功 {summary.ok} / 跳过 {summary.skipped} / 失败 {summary.failed}")
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
