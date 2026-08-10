# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the K8S log getter tool.

Build:
    pyinstaller --clean --noconfirm k8s_log_getter.spec

Output:
    macOS : dist/K8sLogGetter.app
    Windows: dist/K8sLogGetter/K8sLogGetter.exe
"""
import sys

# ---------------- build config ----------------
# 可执行文件名用 ASCII，避免 Windows 中文路径/GBK 编码问题；界面标题仍是中文
APP_NAME = "K8sLogGetter"
ENTRY = "main.py"

# collect PySide6 data/bins/deps (Qt plugins, fonts, etc.)
from PyInstaller.utils.hooks import collect_all

pyside_datas, pyside_bins, pyside_hidden = collect_all("PySide6")
# 应用图标：随包分发，供运行时 setWindowIcon 使用（冻结时位于 _MEIPASS/assets）
icon_datas = [("assets/app_icon.ico", "assets"), ("assets/app_icon.png", "assets")]
# 界面图标：按 色/名.png 组织，icons.py 运行时从 _MEIPASS/assets/icons 取
icon_datas += [("assets/icons", "assets/icons")]
datas = pyside_datas + icon_datas
binaries = pyside_bins
hiddenimports = pyside_hidden + [
    # 第④页 SSH 运维导出 Excel 使用 openpyxl（纯 Python），显式收进包里避免漏打包
    "openpyxl",
    "et_xmlfile",
    # paramiko 依赖的底层库一般能被静态检测到；若打包后运行报缺模块，取消下面注释重新打包
    # "cryptography",
    # "nacl",
    # "bcrypt",
]

block_cipher = None

a = Analysis(
    [ENTRY],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    # runtime hook 修复 PySide6 6.11 冻结环境下 shibokensupport 签名检查崩溃
    runtime_hooks=["rthook_fix_pyside6_signature.py"],
    excludes=["tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 本应用用 QtWidgets + QtCharts（分组统计的柱状/线图）。collect_all + PySide6
# 内置 hook 会把整个 Qt 都收进来（Qt6WebEngineCore.dll≈200M、webengine 资源≈100M、
# qml≈30M、avcodec 多媒体≈20M 等），对 widgets+charts 应用全用不到。在 Analysis
# 合并后的最终产物上按路径/文件名片段剔除；platforms/imageformats 等运行所需
# 插件保留。注意 QtCharts 里含 "charts" 字样，不能按通用词 "charts" 剔除，
# 否则会误删图表库；只按具体用不到的模块名剔除。
_DROP_FRAGMENTS = (
    "webengine", "webchannel", "quick", "quick3d", "quickcontrols2",
    "quickwidgets", "qml", "qmltooling", "qt3d",
    "multimedia", "datavisualization", "graphs", "location", "sensors",
    "positioning", "serialport", "bluetooth", "websockets", "pdf",
    "designer", "metatypes", "avcodec", "avformat", "avutil",
    "swresample", "swscale", "qtopengl", "icudtl", "v8_context",
)


def _drop_path(p) -> bool:
    low = str(p).lower()
    return any(f in low for f in _DROP_FRAGMENTS)


a.binaries = [t for t in a.binaries
              if not _drop_path(t[0]) and not _drop_path(t[1])]
a.datas = [t for t in a.datas
           if not _drop_path(t[0]) and not _drop_path(t[1])
           and not (t[0].lower().endswith(".qm")
                    and "zh_cn" not in t[0].lower())]  # 只留中文本地化
a.pure = [m for m in a.pure if not _drop_path(m[0])]
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    icon="assets/app_icon.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # Qt 应用禁用 UPX：压缩会破坏 DLL 重定位，启动即闪退
    console=False,          # GUI app, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,               # Qt 应用禁用 UPX，理由同上
    upx_exclude=[],
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=APP_NAME + ".app",
        bundle_identifier="com.hy.k8sloggetter",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "1.0.0",
        },
    )
