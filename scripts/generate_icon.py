# scripts/generate_icon.py
"""生成应用图标 assets/app_icon.ico（多尺寸）+ assets/app_icon.png（256px）。

用法（在项目根目录）：
    python scripts/generate_icon.py

说明：
    - 图标设计：蓝底圆角方块 + 三条白色日志线条，寓意日志采集工具。
    - 用 PySide6 绘制后按 PNG 条目打包多尺寸 ICO（Windows 图标规范）。
    - 必须先显式创建 QApplication，否则 QPixmap 隐式建 QGuiApplication
      在部分环境下会崩溃。
"""
import struct
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication

SIZES = [16, 24, 32, 48, 64, 128, 256]
BLUE = QColor("#3b6fc4")
WHITE = QColor("#ffffff")


def make_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    m = size * 0.03
    r = size * 0.18
    path = QPainterPath()
    path.addRoundedRect(QRectF(m, m, size - 2 * m, size - 2 * m), r, r)
    p.fillPath(path, BLUE)
    # 三条日志线条（宽度不同）
    bar_h = max(1.0, size * 0.075)
    gap = size * 0.06
    y0 = size * 0.40
    for i, w in enumerate([0.62, 0.42, 0.74]):
        bp = QPainterPath()
        bp.addRoundedRect(
            QRectF(size * 0.17, y0 + i * (bar_h + gap), size * w, bar_h),
            bar_h / 2, bar_h / 2,
        )
        p.fillPath(bp, WHITE)
    p.end()
    return pm


def pack_ico(pngs: list[tuple[int, bytes]], out: Path) -> None:
    """把 (尺寸, PNG字节) 列表打包成多尺寸 ICO 文件。"""
    count = len(pngs)
    header = struct.pack("<HHH", 0, 1, count)
    entries = []
    offset = 6 + 16 * count
    blob = b""
    for size, png in pngs:
        w = 0 if size >= 256 else size  # 256 在 ICONDIRENTRY 用 0 表示
        entries.append(struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(png), offset))
        blob += png
        offset += len(png)
    out.write_bytes(header + b"".join(entries) + blob)


def main() -> None:
    QApplication([])  # 必须显式创建，见文件头说明
    out = Path("assets")
    out.mkdir(exist_ok=True)
    pngs = []
    for s in SIZES:
        fp = out / ("_icon_%d.png" % s)
        make_pixmap(s).save(str(fp), "PNG")
        pngs.append((s, fp.read_bytes()))
    make_pixmap(256).save(str(out / "app_icon.png"), "PNG")
    pack_ico(pngs, out / "app_icon.ico")
    for s, _ in pngs:
        (out / ("_icon_%d.png" % s)).unlink(missing_ok=True)
    print("OK ico bytes:", (out / "app_icon.ico").stat().st_size,
          "png bytes:", (out / "app_icon.png").stat().st_size,
          "sizes:", len(SIZES))


if __name__ == "__main__":
    main()
