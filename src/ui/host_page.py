# src/ui/host_page.py
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..config import (hosts_from_config, hosts_to_config, load_config,
                      save_config)
from ..models import HostConfig
from ..ssh_client import SSHClient


class _TestWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, host: HostConfig, parent=None):
        super().__init__(parent)
        self.host = host

    def run(self):
        try:
            SSHClient(self.host.ip, self.host.port, self.host.username, self.host.password).connect()
            self.done.emit(True, "连接成功")
        except Exception as e:
            self.done.emit(False, f"连接失败: {e}")


class HostPage(QWidget):
    hostsChanged = Signal()   # 主机列表变更，通知其他页刷新下拉

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hosts = self._load()
        self._worker = None
        self._build_ui()
        self.refresh_table()

    def _load(self):
        data = load_config()
        return hosts_from_config(data)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["IP", "端口", "账号", "备注"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        # 列铺满整行宽度（不再右侧留空）；单元格内容超宽时不折行、自动出横向滚动条
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setWordWrap(False)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.addWidget(self.table, 1)

        form = QVBoxLayout()
        form.addWidget(QLabel("IP:"))
        self.ip_edit = QLineEdit()
        form.addWidget(self.ip_edit)
        form.addWidget(QLabel("端口:"))
        self.port_edit = QLineEdit("22")
        form.addWidget(self.port_edit)
        form.addWidget(QLabel("账号:"))
        self.user_edit = QLineEdit()
        form.addWidget(self.user_edit)
        form.addWidget(QLabel("密码:"))
        self.pwd_edit = QLineEdit()
        self.pwd_edit.setEchoMode(QLineEdit.Password)
        form.addWidget(self.pwd_edit)
        form.addWidget(QLabel("备注:"))
        self.remark_edit = QLineEdit()
        form.addWidget(self.remark_edit)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("新增")
        self.add_btn.setProperty("primary", True)
        self.update_btn = QPushButton("更新")
        self.del_btn = QPushButton("删除")
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.update_btn)
        btn_row.addWidget(self.del_btn)
        form.addLayout(btn_row)
        self.test_btn = QPushButton("测试连接")
        form.addWidget(self.test_btn)
        self.status_label = QLabel("")
        form.addWidget(self.status_label)
        form.addStretch(1)

        wrap = QWidget()
        wrap.setLayout(form)
        layout.addWidget(wrap)

        self.add_btn.clicked.connect(self.add_host)
        self.update_btn.clicked.connect(self.update_host)
        self.del_btn.clicked.connect(self.delete_host)
        self.test_btn.clicked.connect(self.test_connection)
        self.table.itemSelectionChanged.connect(self._load_selected)

    def refresh_table(self):
        self.table.setRowCount(0)
        for i, h in enumerate(self.hosts):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(h.ip))
            self.table.setItem(i, 1, QTableWidgetItem(str(h.port)))
            self.table.setItem(i, 2, QTableWidgetItem(h.username))
            self.table.setItem(i, 3, QTableWidgetItem(h.remark))

    def _load_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.hosts):
            return
        h = self.hosts[row]
        self.ip_edit.setText(h.ip)
        self.port_edit.setText(str(h.port))
        self.user_edit.setText(h.username)
        self.pwd_edit.setText(h.password)
        self.remark_edit.setText(h.remark)

    def _form_host(self):
        return HostConfig(
            ip=self.ip_edit.text().strip(),
            port=int(self.port_edit.text().strip() or 22),
            username=self.user_edit.text().strip(),
            password=self.pwd_edit.text(),
            remark=self.remark_edit.text().strip(),
        )

    def _persist(self):
        data = load_config()
        data["hosts"] = hosts_to_config(self.hosts)
        save_config(data)
        self.refresh_table()
        self.hostsChanged.emit()

    def add_host(self):
        h = self._form_host()
        if not h.ip or not h.username:
            QMessageBox.warning(self, "提示", "IP 和账号必填")
            return
        self.hosts.append(h)
        self._persist()

    def update_host(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择要更新的行")
            return
        self.hosts[row] = self._form_host()
        self._persist()

    def delete_host(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的行")
            return
        del self.hosts[row]
        self._persist()

    def test_connection(self):
        h = self._form_host()
        if not h.ip:
            QMessageBox.warning(self, "提示", "IP 必填")
            return
        self.status_label.setText("测试中...")
        self.test_btn.setEnabled(False)
        self._worker = _TestWorker(h, self)
        self._worker.done.connect(self._on_test_done)
        self._worker.start()

    def _on_test_done(self, ok, msg):
        self.status_label.setText(msg)
        self.test_btn.setEnabled(True)
