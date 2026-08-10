"""分组统计图表弹窗：按字段分组统计的柱状图 + 重启次数分布线图。

数据多时若把统计结果塞进页面内 QLabel 会把界面撑得很大，因此改为
弹出独立对话框展示，主界面保持紧凑。两种图：
- 柱状图：所选字段的值分布（Top N），横轴类别、纵轴 Pod 数
- 线图：按重启次数分布，横轴重启次数（0/1/2/...）、纵轴该次数对应的 Pod 数
"""
from collections import Counter

from PySide6.QtCharts import (QBarCategoryAxis, QBarSeries, QBarSet, QChart,
                              QChartView, QLineSeries, QValueAxis)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPen
from PySide6.QtWidgets import QDialog, QLabel, QTabWidget, QVBoxLayout

from ..models import PodMeta

_ACCENT = "#3b6fc4"      # 与应用主色一致
_TOP_N = 10              # 柱状图最多展示的类别数


def _truncate(s: str, n: int = 16) -> str:
    """超长类别名截断加省略号，避免横轴标签挤成一团。"""
    return s if len(s) <= n else s[:n] + "…"


def _bar_chart(counter: Counter, field_label: str) -> QChart:
    """柱状图：counter 按 (类别, 数量) 降序，取 Top N。"""
    top = counter.most_common(_TOP_N)
    cats = [_truncate(str(k)) for k, _ in top]
    vals = [v for _, v in top]

    bars = QBarSet("Pod 数")
    bars.append(vals)
    series = QBarSeries()
    series.append(bars)

    axis_x = QBarCategoryAxis()
    axis_x.append(cats)
    axis_y = QValueAxis()
    axis_y.setLabelFormat("%d")
    axis_y.setRange(0, max(vals) if vals else 1)

    chart = QChart()
    chart.addSeries(series)
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(axis_x)
    series.attachAxis(axis_y)
    chart.setTitle(f"{field_label} 分布（Top {len(top)}）")
    chart.legend().setVisible(True)
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
    return chart


def _line_chart(metas: list[PodMeta]) -> QChart:
    """线图：按重启次数分布。横轴 0/1/2/... 重启次数，纵轴对应 Pod 数。

    线图需要数值型可排序横轴才有意义，重启次数正好满足；分类字段
    （node/deployName 等）无法排序，适合柱状图而非线图。
    """
    counter = Counter(pm.restart_count for pm in metas)
    xs = sorted(counter)
    series = QLineSeries()
    series.setName("Pod 数")
    for x in xs:
        series.append(float(x), float(counter[x]))

    axis_x = QValueAxis()
    axis_x.setLabelFormat("%d")
    axis_x.setRange(0, max(xs) if xs else 1)
    axis_x.setTickCount(min(len(xs) + 1, 12))
    axis_y = QValueAxis()
    axis_y.setLabelFormat("%d")
    axis_y.setRange(0, max(counter.values()) if counter else 1)
    axis_y.setTickCount(6)

    chart = QChart()
    chart.addSeries(series)
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(axis_x)
    series.attachAxis(axis_y)
    pen = QPen(_ACCENT)
    pen.setWidth(2)
    series.setPen(pen)
    chart.setTitle("重启次数分布")
    chart.legend().setVisible(True)
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
    return chart


class ChartDialog(QDialog):
    """统计图表弹窗：柱状图 + 线图两个标签页，纯展示、可缩放。"""

    def __init__(self, counter: Counter, field_label: str, metas: list[PodMeta],
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"分组统计 - {field_label}")
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        summary = QLabel(f"共 {sum(counter.values())} 个 Pod，按「{field_label}」分组："
                         f"共 {len(counter)} 组")
        summary.setStyleSheet("color: #6a7380;")
        layout.addWidget(summary)

        tabs = QTabWidget()
        tabs.addTab(QChartView(_bar_chart(counter, field_label)), "柱状图")
        tabs.addTab(QChartView(_line_chart(metas)), "线图（重启次数）")
        layout.addWidget(tabs, 1)

    @staticmethod
    def show_stats(counter: Counter, field_label: str, metas: list[PodMeta],
                   parent=None):
        """便捷入口：构造并模态显示统计弹窗。"""
        dlg = ChartDialog(counter, field_label, metas, parent)
        dlg.exec()
