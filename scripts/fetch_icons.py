# -*- coding: utf-8 -*-
"""下载 Feather 图标（MIT）并转成 PNG（双配色），供界面美化使用。

- 源：https://cdn.jsdelivr.net/npm/feather-icons@4.29.2/dist/icons/<名>.svg
- 协议：Feather Icons MIT，允许商用/修改，需保留版权声明（见 assets/icons/README.md）
- 产物：
    assets/icons/svg/<名>.svg          原始 SVG（已缓存则跳过下载）
    assets/icons/accent/<名>.png       主色蓝（普通按钮/导航）
    assets/icons/white/<名>.png        白色（primary 蓝底按钮）

用法：.venv/Scripts/python.exe scripts/fetch_icons.py
依赖 PySide6（本项目的运行依赖，含 QtSvg），无需联网的第三方包。
"""
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVG_DIR = ROOT / "assets" / "icons" / "svg"
# 配色变体：目录名 → 替换进 SVG 的实际颜色（Feather 用 stroke="currentColor"）
VARIANTS = {"accent": "#3b6fc4", "white": "#ffffff"}
PNG_DIRS = {key: ROOT / "assets" / "icons" / key for key in VARIANTS}
ICON_SIZE = 40          # 渲染 40px，运行时由 Qt 缩放到按钮实际图标尺寸，高清屏仍清晰
FEATHER_BASE = "https://cdn.jsdelivr.net/npm/feather-icons@4.29.2/dist/icons"
# 应用里用到的图标（feather 命名）
ICONS = [
    "server", "download", "search", "terminal",          # 左侧导航
    "log-in", "refresh-cw",                              # 连接/刷新
    "plus", "edit-2", "trash-2", "zap",                  # 主机增删改/测试
    "folder", "check-square", "square", "x",             # ②页
    "filter", "bar-chart-2", "file-text", "code",        # ③页/导出
    "play", "stop-circle", "settings", "rotate-ccw", "check",   # ④页/管理
    "chevron-down",                                            # 下拉框箭头
]


def _download_svg(name: str) -> Path:
    """下载单个 SVG，已存在则跳过。网络失败时给出明确错误。"""
    target = SVG_DIR / f"{name}.svg"
    if target.exists():
        return target
    url = f"{FEATHER_BASE}/{name}.svg"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            if resp.status != 200:
                raise RuntimeError(f"{url} → HTTP {resp.status}")
            target.write_bytes(resp.read())
    except Exception as e:
        raise RuntimeError(f"下载 {url} 失败: {e}") from e
    return target


def _render_png(name: str, svg_path: Path, key: str) -> Path:
    """把 SVG 渲染成指定变体颜色的 PNG（用 QtSvg 光栅化，dev 期即可，打包后不需要）。"""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    svg_text = svg_path.read_text(encoding="utf-8")
    svg_text = svg_text.replace("currentColor", VARIANTS[key])   # Feather 描边用 currentColor
    renderer = QSvgRenderer()
    if not renderer.load(svg_text.encode("utf-8")):
        raise RuntimeError(f"SVG 解析失败: {svg_path.name}")

    out_dir = PNG_DIRS[key]
    out_dir.mkdir(parents=True, exist_ok=True)
    img = QImage(ICON_SIZE, ICON_SIZE, QImage.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    # 必须显式给目标矩形，否则部分 QtSvg 版本 render() 不绘制内容
    renderer.render(p, QRectF(0, 0, ICON_SIZE, ICON_SIZE))
    p.end()
    target = out_dir / f"{name}.png"
    if not img.save(str(target)):
        raise RuntimeError(f"PNG 保存失败: {target}")
    return target


def main() -> int:
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    ok, fail = 0, 0
    for name in ICONS:
        try:
            svg = _download_svg(name)
            for color in PNG_DIRS:
                _render_png(name, svg, color)
            ok += 1
            print(f"  [OK]   {name}")
        except Exception as e:
            fail += 1
            print(f"  [FAIL] {name}: {e}")
    print(f"完成：成功 {ok} 个，失败 {fail} 个 → {ROOT / 'assets' / 'icons'}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
