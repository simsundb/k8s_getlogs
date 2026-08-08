# src/ui/host_ns_selector.py
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton,
                               QWidget)

from ..k8s_client import list_namespaces
from ..models import HostConfig
from ..ssh_client import SSHClient
from .icons import set_icon


class HostNamespaceSelector(QWidget):
    """选主机 → 自动连接 → 命名空间下拉。页面②③共用。"""
    connected = Signal(object)        # SSHClient
    namespacesLoaded = Signal(list)   # list[str]
    connectionFailed = Signal(str)
    disconnected = Signal()

    def __init__(self, hosts_provider, parent=None):
        super().__init__(parent)
        self.hosts_provider = hosts_provider
        self._client = None
        self._populating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("SSH主机:"))
        self.host_combo = QComboBox()
        self.host_combo.setMinimumWidth(240)
        layout.addWidget(self.host_combo)
        self.connect_btn = QPushButton("连接")
        self.connect_btn.setProperty("primary", True)
        set_icon(self.connect_btn, "log-in", color="white")
        self.connect_btn.setToolTip("SSH 连接所选主机并自动拉取命名空间列表")
        layout.addWidget(self.connect_btn)
        layout.addSpacing(16)
        layout.addWidget(QLabel("命名空间:"))
        self.ns_combo = QComboBox()
        self.ns_combo.setMinimumWidth(260)
        layout.addWidget(self.ns_combo)
        self.refresh_btn = QPushButton("刷新")
        set_icon(self.refresh_btn, "refresh-cw")
        self.refresh_btn.setToolTip("重新拉取命名空间列表")
        layout.addWidget(self.refresh_btn)
        layout.addStretch(1)

        self.connect_btn.clicked.connect(self.connect_now)
        self.refresh_btn.clicked.connect(self.refresh_namespaces)
        self.host_combo.currentIndexChanged.connect(self._on_host_changed)

    def refresh_hosts(self):
        self._populating = True
        try:
            self.host_combo.clear()
            for h in self.hosts_provider():
                self.host_combo.addItem(f"{h.ip}:{h.port} ({h.username})", h)
        finally:
            self._populating = False
        if self.host_combo.count():
            self.host_combo.setCurrentIndex(0)

    def current_host(self) -> HostConfig:
        return self.host_combo.currentData()

    def client(self) -> SSHClient:
        return self._client

    def connect_now(self):
        host = self.current_host()
        if host is None:
            self.connectionFailed.emit("请先在「主机配置」页添加主机")
            return
        try:
            client = SSHClient(host.ip, host.port, host.username, host.password).connect()
        except Exception as e:
            self.connectionFailed.emit(f"连接 {host.ip} 失败: {e}")
            return
        if self._client:
            self._client.close()
        self._client = client
        self.connected.emit(client)
        self.refresh_namespaces()

    def _on_host_changed(self, index):
        if self._populating:
            return
        if self._client:
            self._client.close()
            self._client = None
            self.disconnected.emit()
        self.ns_combo.clear()
        if self.host_combo.count() and index >= 0:
            self.connect_now()

    def refresh_namespaces(self):
        if not self._client:
            self.connectionFailed.emit("尚未连接")
            return
        try:
            nss = list_namespaces(self._client)
        except Exception as e:
            self.connectionFailed.emit(str(e))
            return
        self.ns_combo.clear()
        self.ns_combo.addItems(nss)
        self.namespacesLoaded.emit(nss)
