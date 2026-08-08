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
# ③ 页分组统计使用 QtCharts（PySide6 自带模块，但冻结包需单独收集其插件数据）
charts_datas, charts_bins, charts_hidden = collect_all("PySide6.QtCharts")
datas = pyside_datas + charts_datas
binaries = pyside_bins + charts_bins
hiddenimports = pyside_hidden + charts_hidden + [
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
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
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
