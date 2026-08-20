@echo off
REM ============================================
REM Build script for Windows (PyInstaller)
REM Usage: run build.bat in project root
REM Output: dist\K8sLogGetter\K8sLogGetter.exe
REM ============================================
setlocal

cd /d "%~dp0"

REM 检查 Python 是否可用
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH. Please install Python 3.8+.
    pause
    exit /b 1
)

REM 检查虚拟环境，若缺失则创建并安装依赖
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    
    echo [2/4] Installing project dependencies...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install project dependencies.
        echo        Check requirements.txt or network connection.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Virtual environment .venv already exists, skipping creation.
)

echo [2/4] Installing/upgrading build dependencies...
".venv\Scripts\python.exe" -m pip install -q --upgrade pyinstaller
if errorlevel 1 (
    echo [ERROR] Failed to install pyinstaller.
    pause
    exit /b 1
)

echo [3/4] Cleaning old artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/4] Building with PyInstaller...
".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm k8s_log_getter.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo Build complete!
echo Output: dist\K8sLogGetter\K8sLogGetter.exe
echo Package the whole "dist\K8sLogGetter" folder to distribute.
echo ============================================
echo.
pause
goto :eof