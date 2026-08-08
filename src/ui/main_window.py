from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QStackedWidget,
                               QWidget)

from ..config import hosts_from_config, load_config
from .analyze_page import AnalyzePage
from .collect_page import CollectPage
from .host_page import HostPage
from .ops_page import OpsPage

APP_TITLE = "资源管控中心-k8s日志采集工具"
APP_AUTHOR = "SunZH"


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 720)

        central = QWidget()
        layout = QHBoxLayout(central)
        self.nav = QListWidget()
        self.nav.setFixedWidth(150)
        for name in ("① 主机配置", "② 日志抓取", "③ 查询分析", "④ SSH 运维"):
            self.nav.addItem(QListWidgetItem(name))
        layout.addWidget(self.nav)

        self.stack = QStackedWidget()
        self.host_page = HostPage(self)
        self.collect_page = CollectPage(self._hosts_provider, self)
        self.analyze_page = AnalyzePage(self._hosts_provider, self)
        self.ops_page = OpsPage(self._hosts_provider, self)
        self.stack.addWidget(self.host_page)
        self.stack.addWidget(self.collect_page)
        self.stack.addWidget(self.analyze_page)
        self.stack.addWidget(self.ops_page)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        self.host_page.hostsChanged.connect(self._refresh_selector_hosts)
        self._refresh_selector_hosts()

        self._build_statusbar()

    def _hosts_provider(self):
        return hosts_from_config(load_config())

    def _refresh_selector_hosts(self):
        self.collect_page.selector.refresh_hosts()
        self.analyze_page.selector.refresh_hosts()
        self.ops_page.selector.refresh_hosts()

    def _build_statusbar(self):
        bar = self.statusBar()
        bar.showMessage(f"作者：{APP_AUTHOR}")
        self._page_name = ""
        self.status_right = QLabel("")
        bar.addPermanentWidget(self.status_right)
        self.nav.currentRowChanged.connect(self._on_page_changed)
        self._on_page_changed(0)
        # 每秒刷新右侧「当前页面 + 日期时间」
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick)
        self._clock.start(1000)
        self._tick()

    def _on_page_changed(self, row):
        self._page_name = self.nav.item(row).text() if row >= 0 else ""

    def _tick(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.status_right.setText(f"{self._page_name}　{now}")
