#!/usr/bin/env bash
# 构建脚本：用 PyInstaller 打包 K8S 日志采集与分析工具
#
# macOS:   ./build.sh
# Windows: 在 cmd/powershell 里运行 build.bat（或手动执行）
#          pyinstaller --clean --noconfirm k8s_log_getter.spec
#
# 产物:
#   macOS  -> dist/K8sLogGetter.app   (若系统支持还会生成 dist/K8sLogGetter.dmg)
#   Windows-> dist/K8sLogGetter/K8sLogGetter.exe
#
# 注意: 交叉打包不受支持——macOS 包只能在 macOS 上打，Windows 包只能在 Windows 上打。
set -e

cd "$(dirname "$0")"

echo "==> 安装构建依赖"
PYTHON="python3"
if [ -x "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
fi
"$PYTHON" -m pip install -q pyinstaller

echo "==> 清理旧产物"
rm -rf build dist

echo "==> PyInstaller 打包"
"$PYTHON" -m PyInstaller --clean --noconfirm k8s_log_getter.spec

echo ""
echo "==> 完成"
if [ -d "dist/K8sLogGetter.app" ]; then
    echo "macOS 产物: dist/K8sLogGetter.app"
    # 去除隔离标记, 对方双击即可打开（本机开发的 Mac 不会加标记，但从
    # 网上下载/拷贝过的文件可能有，统一清一次无害）
    xattr -cr "dist/K8sLogGetter.app"
    # 可选: 生成 dmg 安装镜像
    if command -v hdiutil >/dev/null 2>&1; then
        echo ""
        echo "==> 生成 DMG 安装镜像"
        rm -f "dist/K8sLogGetter.dmg"
        hdiutil create -volname "K8sLogGetter" -srcfolder "dist/K8sLogGetter.app" \
            -ov -format UDZO "dist/K8sLogGetter.dmg" >/dev/null
        echo "DMG 产物: dist/K8sLogGetter.dmg"
    fi
elif [ -d "dist/K8sLogGetter" ]; then
    echo "Windows 产物: dist/K8sLogGetter/"
fi
