import logging

import pytest

def _fresh(monkeypatch):
    import src.logger as L
    monkeypatch.setattr(L, "_configured", False)
    return L

@pytest.fixture(autouse=True)
def _cleanup_log_handlers():
    root = logging.getLogger()
    before = set(root.handlers)
    yield
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()

def test_logger_writes_to_file(tmp_path, monkeypatch):
    L = _fresh(monkeypatch)
    log_dir = tmp_path / "logs"
    log_file = L.setup_logging(log_dir)
    assert log_file.name == "app.log"
    logging.getLogger("test").info("hello-123")
    assert log_file.exists()
    assert "hello-123" in log_file.read_text(encoding="utf-8")

def test_setup_idempotent_no_duplicate_handlers(tmp_path, monkeypatch):
    L = _fresh(monkeypatch)
    L.setup_logging(tmp_path)
    before = len(logging.getLogger().handlers)
    L.setup_logging(tmp_path)
    assert len(logging.getLogger().handlers) == before
