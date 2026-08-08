import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_configured = False

def setup_logging(log_dir: Path) -> Path:
    """初始化根 logger：文件轮转 + 控制台。返回日志文件路径。"""
    global _configured
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    if _configured:
        return log_file
    root.setLevel(logging.DEBUG)
    fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)
    root.addHandler(ch)
    _configured = True
    return log_file
