from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QListWidgetItem,
                               QMainWindow, QStackedWidget, QWidget)

from ..config import hosts_from_config, load_config
from .analyze_page import AnalyzePage
from .collect_page import CollectPage
from .host_page import HostPage


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("K8S 日志采集与分析工具")
        self.resize(1100, 720)

        central = QWidget()
        layout = QHBoxLayout(central)
        self.nav = QListWidget()
        self.nav.setFixedWidth(150)
        for name in ("① 主机配置", "② 日志抓取", "③ 查询分析"):
            self.nav.addItem(QListWidgetItem(name))
        layout.addWidget(self.nav)

        self.stack = QStackedWidget()
        self.host_page = HostPage(self)
        self.collect_page = CollectPage(self._hosts_provider, self)
        self.analyze_page = AnalyzePage(self._hosts_provider, self)
        self.stack.addWidget(self.host_page)
        self.stack.addWidget(self.collect_page)
        self.stack.addWidget(self.analyze_page)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        self.host_page.hostsChanged.connect(self._refresh_selector_hosts)
        self._refresh_selector_hosts()

    def _hosts_provider(self):
        return hosts_from_config(load_config())

    def _refresh_selector_hosts(self):
        self.collect_page.selector.refresh_hosts()
        self.analyze_page.selector.refresh_hosts()
