# src/ui/ops_page.py
"""第④页「SSH 运维」：预置运维命令 + 自定义命令，SSH 执行并回显，支持导出 Excel / HTML。"""
import time
from datetime import datetime

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from ..config import load_config, save_config
from ..models import HostConfig
from ..ops import (OpsCommand, OpsResult, build_command, export_excel,
                   export_html, load_ops_commands, save_ops_commands)
from ..ssh_client import SSHClient
from .host_ns_selector import HostNamespaceSelector
from .icons import set_icon
from .log_panel import LogPanel
from .ops_manager import OpsManagerDialog


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class _OpsWorker(QThread):
    """后台线程：自建 SSH 连接执行单条命令，避免阻塞 UI 且不跨线程复用主连接。"""
    result_ready = Signal(object)   # OpsResult

    def __init__(self, host: HostConfig, label: str, command: str, parent=None):
        super().__init__(parent)
        self.host = host
        self.label = label
        self.command = command
        self._client = None
        self._cancelled = False

    def cancel_request(self) -> None:
        self._cancelled = True
        if self._client:
            try:
                self._client.close()   # 中断阻塞中的读，让 run() 尽快退出
            except Exception:
                pass

    def run(self):
        start = time.time()
        client = SSHClient(self.host.ip, self.host.port, self.host.username,
                           self.host.password)
        try:
            client.connect()
            self._client = client
            code, out, err = client.exec_stdout(self.command, timeout=600)
            duration = round(time.time() - start, 2)
            if self._cancelled:
                res = OpsResult(self.label, self.command, _now(), False,
                                error="已手动停止", duration=duration)
            else:
                res = OpsResult(self.label, self.command, _now(), code == 0,
                                output=out, error=err.strip(),
                                exit_code=code, duration=duration)
        except Exception as e:
            duration = round(time.time() - start, 2)
            if self._cancelled:
                res = OpsResult(self.label, self.command, _now(), False,
                                error="已手动停止", duration=duration)
            else:
                res = OpsResult(self.label, self.command, _now(), False,
                                error=str(e), duration=duration)
        finally:
            try:
                client.close()
            except Exception:
                pass
            self._client = None
        self.result_ready.emit(res)


class OpsPage(QWidget):
    def __init__(self, hosts_provider, parent=None):
        super().__init__(parent)
        self._worker = None
        self.results: list[OpsResult] = []
        # 运维项清单：config.json 有保存则用保存的，否则用出厂预置
        self.commands: list[OpsCommand] = load_ops_commands(load_config())

        root = QVBoxLayout(self)
        self.selector = HostNamespaceSelector(hosts_provider, self)
        root.addWidget(self.selector)

        # ---- 预置运维命令 ----
        group = QGroupBox("日常运维（预置命令）")
        gl = QVBoxLayout(group)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("类别:"))
        self.cat_combo = QComboBox()
        # 默认选中「全部」时若没有最小宽度，AdjustToContents 会把盒子收缩到
        # 单字那么窄（57px），看起来很小气；给一个合理下限保持正常宽度
        self.cat_combo.setMinimumWidth(120)
        self.cat_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        row1.addWidget(self.cat_combo)
        row1.addWidget(QLabel("运维项:"))
        self.cmd_combo = QComboBox()
        self.cmd_combo.setMinimumWidth(280)
        # 运维项是动态加载的「[类别] 名称」，随内容自适应宽度，避免长项被截断
        self.cmd_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        row1.addWidget(self.cmd_combo, 1)
        self.run_btn = QPushButton("执行")
        self.run_btn.setProperty("primary", True)
        set_icon(self.run_btn, "play", color="white")
        self.run_btn.setToolTip("SSH 到 MASTER 执行选中的预置运维命令")
        row1.addWidget(self.run_btn)
        self.manage_btn = QPushButton("管理运维项")
        set_icon(self.manage_btn, "settings")
        self.manage_btn.setToolTip("新增/编辑/删除/停用预置运维命令")
        row1.addWidget(self.manage_btn)
        gl.addLayout(row1)
        self.cmd_desc = QLabel("")
        self.cmd_desc.setWordWrap(True)
        self.cmd_desc.setStyleSheet("color: #6a7380;")
        gl.addWidget(self.cmd_desc)
        root.addWidget(group)

        # ---- 自定义命令 ----
        cgroup = QGroupBox("自动化运维（自定义命令）")
        cl = QHBoxLayout(cgroup)
        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText(
            "输入任意 shell / kubectl 命令，回车执行，例如：kubectl get pods -A | grep CrashLoopBackOff")
        cl.addWidget(self.custom_edit, 1)
        self.custom_run_btn = QPushButton("执行")
        self.custom_run_btn.setProperty("primary", True)
        set_icon(self.custom_run_btn, "terminal", color="white")
        self.custom_run_btn.setToolTip("执行输入框中的自定义命令")
        cl.addWidget(self.custom_run_btn)
        self.stop_btn = QPushButton("停止")
        set_icon(self.stop_btn, "stop-circle")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("中断正在执行的长命令")
        cl.addWidget(self.stop_btn)
        root.addWidget(cgroup)

        # ---- 输出回显 ----
        out_header = QHBoxLayout()
        out_header.addWidget(QLabel("输出结果:"))
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #6a7380;")
        out_header.addWidget(self.status_label, 1)
        root.addLayout(out_header)
        self.log_panel = LogPanel()
        root.addWidget(self.log_panel, 1)

        # ---- 导出 ----
        exp = QHBoxLayout()
        self.export_excel_btn = QPushButton("导出 Excel")
        set_icon(self.export_excel_btn, "file-text")
        self.export_excel_btn.setToolTip("导出为 xlsx（每命令一个工作表 + 汇总表）")
        self.export_html_btn = QPushButton("导出 HTML")
        set_icon(self.export_html_btn, "code")
        self.export_html_btn.setToolTip("导出为独立 HTML 报告")
        self.clear_btn = QPushButton("清空输出")
        set_icon(self.clear_btn, "trash-2")
        self.clear_btn.setToolTip("清空输出区与已收集的结果")
        exp.addWidget(self.export_excel_btn)
        exp.addWidget(self.export_html_btn)
        exp.addWidget(self.clear_btn)
        exp.addStretch(1)
        root.addLayout(exp)

        # ---- 信号 ----
        self.selector.connectionFailed.connect(self._on_error)
        self.selector.ns_combo.currentIndexChanged.connect(
            lambda _i: self._show_cmd_desc())
        self.cat_combo.currentIndexChanged.connect(self._reload_cmds)
        self.cmd_combo.currentIndexChanged.connect(self._show_cmd_desc)
        self.run_btn.clicked.connect(self._run_predefined)
        self.manage_btn.clicked.connect(self._open_manager)
        self.custom_run_btn.clicked.connect(self._run_custom)
        self.custom_edit.returnPressed.connect(self._run_custom)
        self.stop_btn.clicked.connect(self._stop)
        self.export_excel_btn.clicked.connect(self._export_excel)
        self.export_html_btn.clicked.connect(self._export_html)
        self.clear_btn.clicked.connect(self._clear)

        self._refresh_categories()
        self._reload_cmds()
        self._update_export_state()

    # ---------- 预置命令 ----------
    def _refresh_categories(self):
        """按当前启用命令重建类别下拉（停用命令的类别不出现）。"""
        cats: list[str] = []
        for c in self.commands:
            if c.active and c.category not in cats:
                cats.append(c.category)
        self.cat_combo.blockSignals(True)
        self.cat_combo.clear()
        self.cat_combo.addItem("全部")
        self.cat_combo.addItems(cats)
        self.cat_combo.blockSignals(False)

    def _reload_cmds(self):
        cat = self.cat_combo.currentText()
        cmds = [c for c in self.commands
                if c.active and (cat == "全部" or c.category == cat)]
        self.cmd_combo.blockSignals(True)
        self.cmd_combo.clear()
        for c in cmds:
            self.cmd_combo.addItem(f"[{c.category}] {c.label}", c)
        self.cmd_combo.blockSignals(False)
        if self.cmd_combo.count():
            self.cmd_combo.setCurrentIndex(0)
        self._show_cmd_desc()

    def _open_manager(self):
        """打开运维项管理对话框，保存后重建下拉并写回 config.json。"""
        dlg = OpsManagerDialog(self.commands, self)
        if dlg.exec() == QDialog.Accepted:
            self.commands = dlg.commands()
            data = load_config()
            save_ops_commands(data, self.commands)
            save_config(data)
            self._refresh_categories()
            self._reload_cmds()
            self.log_panel.append_log(
                f"运维项已保存：共 {len(self.commands)} 项，"
                f"启用 {sum(1 for c in self.commands if c.active)} 项")

    def _show_cmd_desc(self):
        cmd = self.cmd_combo.currentData()
        if cmd is None:
            self.cmd_desc.setText("")
            return
        ns = self.selector.ns_combo.currentText()
        resolved = build_command(cmd.command, ns)
        need = "（需先选择命名空间）" if cmd.needs_namespace and not ns else ""
        self.cmd_desc.setText(
            f"说明：{cmd.description}{need}\n将执行：{resolved}")

    # ---------- 执行 ----------
    def _run_predefined(self):
        cmd: OpsCommand | None = self.cmd_combo.currentData()
        if cmd is None:
            return
        ns = self.selector.ns_combo.currentText()
        if cmd.needs_namespace and not ns:
            self.log_panel.append_log("[错误] 请先在顶部连接主机并选择命名空间")
            return
        self._start(cmd.label, build_command(cmd.command, ns))

    def _run_custom(self):
        text = self.custom_edit.text().strip()
        if not text:
            self.log_panel.append_log("[提示] 请先输入要执行的命令")
            return
        self._start("自定义命令", text)

    def _start(self, label: str, command: str):
        if self._worker and self._worker.isRunning():
            self.log_panel.append_log("[提示] 上一条命令仍在执行中，请等待或点击「停止」")
            return
        host = self.selector.current_host()
        if host is None:
            self.log_panel.append_log("[错误] 未选择主机，请先在「主机配置」页添加主机")
            return
        self._set_running(True)
        self.log_panel.append_log(f"→ 执行 [{label}]：{command}")
        self.status_label.setText("正在执行...")
        self._worker = _OpsWorker(host, label, command, self)
        self._worker.result_ready.connect(self._on_result)
        self._worker.start()

    def _on_result(self, res: OpsResult):
        self.results.append(res)
        self.log_panel.append_log(res.display())
        self.log_panel.append_log("")
        self.status_label.setText(f"完成：{res.status}，共执行 {len(self.results)} 条")
        self._set_running(False)
        self._update_export_state()
        self._worker = None

    def _stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel_request()
            self.log_panel.append_log("→ 已发送停止请求，正在中断...")
            self.status_label.setText("正在停止...")

    def _set_running(self, running: bool):
        self.run_btn.setEnabled(not running)
        self.custom_run_btn.setEnabled(not running)
        self.custom_edit.setEnabled(not running)
        self.stop_btn.setEnabled(running)

    # ---------- 导出 / 清空 ----------
    def _update_export_state(self):
        has = bool(self.results)
        self.export_excel_btn.setEnabled(has)
        self.export_html_btn.setEnabled(has)

    def _export_excel(self):
        if not self.results:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Excel", "ops_results.xlsx", "Excel 文件 (*.xlsx)")
        if not path:
            return
        try:
            export_excel(self.results, path)
        except Exception as e:
            self._on_error(f"导出 Excel 失败: {e}")
            return
        self.log_panel.append_log(f"已导出 Excel：{path}")

    def _export_html(self):
        if not self.results:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 HTML", "ops_results.html", "HTML 文件 (*.html)")
        if not path:
            return
        try:
            export_html(self.results, path)
        except Exception as e:
            self._on_error(f"导出 HTML 失败: {e}")
            return
        self.log_panel.append_log(f"已导出 HTML：{path}")

    def _clear(self):
        self.log_panel.clear_log()
        self.results.clear()
        self.status_label.setText("就绪")
        self._update_export_state()

    def _on_error(self, msg: str):
        self.log_panel.append_log(f"[错误] {msg}")

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.cancel_request()
            self._worker.wait(3000)
        self._worker = None
        super().closeEvent(event)
