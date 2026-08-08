# 图标资源

本目录图标来自 **Feather Icons**（MIT 协议，允许商用/修改/分发，需保留版权声明）。

- 源：`https://cdn.jsdelivr.net/npm/feather-icons@4.29.2/dist/icons/<名>.svg`
- Feather 版权：© 2013-2023 Cole Bemis（MIT License）
- 重新生成：`.venv/Scripts/python.exe scripts/fetch_icons.py`（从 jsdelivr 下载 SVG → QtSvg 渲染成 PNG）

## 结构

```
svg/      原始 SVG（下载缓存，可重新生成）
accent/   主色蓝 #3b6fc4（普通按钮 / 左侧导航）
white/    白色（primary 蓝底按钮上的图标）
```

## 使用

运行时经 `src/ui/icons.py` 加载：

```python
from .icons import icon, set_icon
btn.setIcon(icon("refresh-cw"))      # accent 色
set_icon(btn, "plus", color="white")  # 白色 + 统一尺寸
```

打包时由 `k8s_log_getter.spec` 的 `datas` 连同 `assets/app_icon.*` 一起收进 exe。
