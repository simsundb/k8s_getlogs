# K8S 日志采集与分析工具 —— 打包与分发说明

本文档说明如何把本工具打包成可独立运行的桌面应用（Windows 可执行程序 / macOS App），以及分发时的注意事项。参考同父目录下 LOG_ANALYZE 项目的 PyInstaller 打包方案改造而来。

## 概述

- 打包工具：**PyInstaller**（把 Python 源码 + 解释器 + 第三方库打包成独立程序，目标机器无需安装 Python）
- 技术栈：PySide6（GUI）、paramiko（SSH）
- 文件：
  | 文件 | 作用 |
  |------|------|
  | `build.bat` | Windows 打包脚本 |
  | `build.sh` | macOS / Linux 打包脚本 |
  | `k8s_log_getter.spec` | PyInstaller 打包配置（两脚本共用） |
  | `rthook_fix_pyside6_signature.py` | 运行时钩子，规避 PySide6 冻结环境下的签名检查崩溃 |
  | 本文档 | 打包与分发说明 |
- 打包产物位于 `build/` 与 `dist/` 目录，**已加入 `.gitignore`，不会提交到 git**；上述脚本与配置文件属于源码，可正常提交。

## 环境要求

- **Python 3.10 或更高**（代码使用了 `X | None` 等 3.10 语法）
- 运行依赖：`python -m pip install -r requirements.txt`（PySide6、paramiko）
- `pyinstaller` 由构建脚本自动安装，无需手动装
- 打包机需能访问 pip 源

## Windows 打包

1. 打开 cmd 或 PowerShell，`cd` 到项目根目录
2. 运行 `build.bat`
3. 产物：`dist\K8sLogGetter\K8sLogGetter.exe` —— 整个 `dist\K8sLogGetter\` 文件夹即为可分发包

脚本做三件事：安装 pyinstaller → 清理旧的 `build/`、`dist/` → 用 `k8s_log_getter.spec` 打包。

## macOS 打包

1. 打开终端，`cd` 到项目根目录
2. 运行 `./build.sh`（首次若提示无权限：`chmod +x build.sh`）
3. 产物：`dist/K8sLogGetter.app`；若系统安装了 `hdiutil`，还会额外生成 `dist/K8sLogGetter.dmg`

脚本优先使用 `venv/bin/python`，否则回退到系统 `python3`；随后安装 pyinstaller → 清理 → 打包 → 输出 `.app`（可选生成 dmg）。

> **注意：PyInstaller 不支持交叉打包** —— macOS 的 `.app` 只能在 macOS 上构建，Windows 的 `.exe` 只能在 Windows 上构建。

## 分发注意事项

### Windows
- 将 `dist\K8sLogGetter\` 整个文件夹压缩成 zip 分发即可，对方无需安装 Python
- 首次运行若被杀毒软件拦截，通常是 PyInstaller 打包程序的误报，添加白名单即可
- exe 双击启动，无控制台窗口

### macOS
- 分发 `.app` 或 `.dmg`
- **未签名/未公证的 app 在对方机器上首次打开可能提示「无法验证开发者」**：
  - 对方可在「系统设置 → 隐私与安全性」中点击「仍要打开」；或
  - 分发前在本机执行 `xattr -cr dist/K8sLogGetter.app` 去除隔离属性（脚本完成后会提示）
  - 要彻底解决需 Apple 开发者账号对包签名 + 公证，超出本文档范围

### 通用
- 配置与日志位置不受打包影响：`~/.k8s_log_getter/config.json`、`~/.k8s_log_getter/logs/app.log`
- 本工具通过 SSH 连接 K8S Master 执行 kubectl；运行环境需能网络访问集群，且 Master 上 `kubectl` 可用
- 日志默认存软件运行目录下 `output/`，可在页面②「选择存储目录」修改

## 打包后快速验证

1. 启动程序，切到「① 主机配置」
2. 新增一个真实可用的主机，点「测试连接」应提示成功
3. 切到「② 日志抓取」，选择命名空间后应能看到 Pod 列表

## 常见问题

| 现象 | 原因 / 解决 |
|------|-------------|
| 打包后启动报「找不到模块」 | 模块是动态导入、未被静态检测到；把模块名加入 `k8s_log_getter.spec` 的 `hiddenimports` 后重新打包 |
| PySide6 冻结环境启动崩溃（shibokensupport 签名检查 / `inspect.getsource` 报错） | 已内置 `rthook_fix_pyside6_signature.py` 规避；若仍复现，确认 spec 的 `runtime_hooks` 里包含该文件 |
| paramiko 报缺 `cryptography` / `nacl` / `bcrypt` | 把对应包名加入 `hiddenimports`（spec 内已留有注释位） |
| Windows 上 exe 被杀软删除 | 添加白名单；或调整打包参数重新构建 |
| 想换应用图标 | 准备 `.ico`（Windows）与 `.icns`（macOS），在 spec 的 `EXE` / `BUNDLE` 中指定 `icon` |

## 不提交到 git 的产物

`build/`、`dist/`（含 `.dmg`）、`*.spec.bak` 已在 `.gitignore` 中排除。构建脚本 `build.bat`、`build.sh`、打包配置 `k8s_log_getter.spec`、运行时钩子 `rthook_fix_pyside6_signature.py` 及本文档属于源码，可提交。
