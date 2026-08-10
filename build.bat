@echo off
REM ============================================
REM Build script for Windows (PyInstaller)
REM Usage: run build.bat in project root
REM Output: dist\K8sLogGetter\K8sLogGetter.exe
REM ============================================
setlocal

cd /d "%~dp0"

REM 优先用项目虚拟环境（与 build.sh 逻辑一致）；不存在才回退系统 python。
REM 裸 python 可能落到系统解释器，其 PySide6 版本与开发环境不一致。
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

echo [1/3] Installing build dependencies...
%PY% -m pip install -q pyinstaller
if errorlevel 1 goto :fail

echo [2/3] Cleaning old artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] Building with PyInstaller...
%PY% -m PyInstaller --clean --noconfirm k8s_log_getter.spec
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
