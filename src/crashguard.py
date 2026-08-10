"""启动期崩溃兜底：把冻结 GUI 应用「一闪而过」的崩溃写到文件。

打包版 console=False 时，Python 异常与原生段错误都没有可见输出，
窗口一闪就退出、app.log 也可能来不及写。此模块在 main.py 最顶部、
早于任何第三方库 import，注册：
- faulthandler：捕获 C 层段错误（segfault / DLL 加载失败），写入 crash.log
- sys.excepthook：捕获未处理 Python 异常，写 crash.log + 尽力弹窗提示

之后无论崩在哪一步，都能在 ~/.k8s_log_getter/logs/crash.log 找到真实原因。
"""
import faulthandler
import sys
import traceback
from pathlib import Path

_CRASH_DIR = Path.home() / ".k8s_log_getter" / "logs"
_CRASH_FILE = _CRASH_DIR / "crash.log"
_fh = None  # 保持 faulthandler 文件流引用不释放


def _write(msg: str) -> None:
    try:
        _CRASH_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CRASH_FILE, "a", encoding="utf-8") as f:
            f.write(msg)
            f.write("\n" + "=" * 60 + "\n")
    except OSError:
        pass


def _install():
    global _fh
    try:
        _CRASH_DIR.mkdir(parents=True, exist_ok=True)
        _fh = open(_CRASH_FILE, "a", encoding="utf-8")
        faulthandler.enable(file=_fh)
    except OSError:
        pass
    _write("[startup] crashguard 已启用，崩溃详情将写入: " + str(_CRASH_FILE))

    def _excepthook(exc_type, exc_val, exc_tb):
        tb = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
        _write("[unhandled exception]\n" + tb)
        # 非阻塞弹窗提示崩溃已记录，不阻塞退出流程（QMessageBox.critical 会阻塞挂起）
        try:
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication(sys.argv)
            QTimer.singleShot(0, lambda: QMessageBox.critical(
                None, "程序发生错误",
                f"程序出错即将退出。\n详情已写入：\n{_CRASH_FILE}\n\n{tb[-2000:]}"))
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_val, exc_tb)

    sys.excepthook = _excepthook


_install()
