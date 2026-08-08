@echo off
REM ============================================
REM Build script for Windows (PyInstaller)
REM Usage: run build.bat in project root
REM Output: dist\K8sLogGetter\K8sLogGetter.exe
REM ============================================
setlocal

cd /d "%~dp0"

echo [1/3] Installing build dependencies...
python -m pip install -q pyinstaller
if errorlevel 1 goto :fail

echo [2/3] Cleaning old artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] Building with PyInstaller...
python -m PyInstaller --clean --noconfirm k8s_log_getter.spec
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
