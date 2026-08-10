@echo off
REM ============================================
REM Build script for Windows (PyInstaller)
REM Usage: run build.bat in project root
REM Output: dist\K8sLogGetter\K8sLogGetter.exe
REM ============================================
setlocal

cd /d "%~dp0"

REM 优先用项目虚拟环境，保证依赖与开发环境一致（与 build.sh 逻辑对齐）。
REM mac 拷贝来的 .venv 在 Windows 不可用；若缺失则自动创建并安装依赖（仅首次较慢）。
if not exist ".venv\Scripts\python.exe" (
    echo [0/3] Creating virtual environment .venv ...
    python -m venv .venv
    if errorlevel 1 goto :fail
    echo      Installing project dependencies (PySide6, paramiko...) ...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :fail
)

echo [1/3] Installing build dependencies...
".venv\Scripts\python.exe" -m pip install -q pyinstaller
if errorlevel 1 goto :fail

echo [2/3] Cleaning old artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] Building with PyInstaller...
".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm k8s_log_getter.spec
if errorlevel 1 goto :fail

echo.
echo Build complete!
echo Output: dist\K8sLogGetter\K8sLogGetter.exe
echo Package the whole "dist\K8sLogGetter" folder to distribute.
goto :eof

:fail
echo.
echo Build FAILED. Check the error above.
exit /b 1

endlocal
