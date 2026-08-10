import json
import sys
import tarfile
import zipfile
from pathlib import Path
from threading import Event

from src.collector import (Collector, aggregate_logs, extract_tar,
                           write_manifest, zip_output)
from src.config import software_dir
from src.models import DEFAULT_LOG_DIR, CollectResult, CollectTask, PodMeta


class _FakeSSH:
    """用本地真实 tar 模拟远端 tar 输出。stream_to_file 忽略命令，打包 source_dir。"""

    def __init__(self, source_dir: Path):
        self.source_dir = source_dir

    def stream_to_file(self, command, filepath, timeout=600):
        with tarfile.open(filepath, "w:gz") as tf:
            for p in sorted(self.source_dir.rglob("*")):
                if p.is_file():
                    tf.add(p, arcname=p.relative_to(self.source_dir))
        return 0

    def close(self):
        pass


class _RecordingSSH:
    """记录远端 tar 命令并输出真实 tar，用于断言 log_dir 被传入。"""

    def __init__(self, source_dir: Path):
        self.source_dir = source_dir
        self.last_cmd = ""

    def stream_to_file(self, command, filepath, timeout=600):
        self.last_cmd = command
        with tarfile.open(filepath, "w:gz") as tf:
            for p in sorted(self.source_dir.rglob("*")):
                if p.is_file():
                    tf.add(p, arcname=p.relative_to(self.source_dir))
        return 0

    def close(self):
        pass


class _CorruptStreamClient:
    """stream_to_file 写入损坏的 tar 数据，模拟下载后解析失败（count_tar_files 抛错）。"""

    def __init__(self, payload=b"not a gzip"):
        self.payload = payload
        self.closed = False

    def stream_to_file(self, command, filepath, timeout=600):
        Path(filepath).write_bytes(self.payload)
        return 0

    def close(self):
        self.closed = True


def _make_source(root: Path, files: dict) -> Path:
    src = root / "opt_logs"
    for rel, content in files.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return src


def test_collect_task_default_log_dir():
    assert CollectTask("p", "d", "ns", "*.log").log_dir == DEFAULT_LOG_DIR


def test_collector_uses_task_log_dir(tmp_path):
    src = _make_source(tmp_path, {"a.log": "x"})
    fake = _RecordingSSH(src)
    collector = Collector(lambda: fake, tmp_path / "output", max_workers=1)
    task = CollectTask(pod_name="podX", deploy_name="app", namespace="ns",
                       pattern="*.log", log_dir="/data/logs")
    results = collector.run([task], cancel=Event())
    assert results[0].ok is True
    assert "cd /data/logs" in fake.last_cmd


def test_extract_tar(tmp_path):
    src = _make_source(tmp_path, {"a.log": "aaa", "b.log": "bbb"})
    fake = _FakeSSH(src)
    tar = tmp_path / "p.tar.gz"
    fake.stream_to_file("ignored", tar)
    dest = tmp_path / "dest"
    count, total = extract_tar(tar, dest)
    assert count == 2
    assert total == 6  # "aaa"(3) + "bbb"(3) 的未压缩字节数
    assert (dest / "a.log").read_text() == "aaa"


def test_collector_runs_tasks_and_writes_layout(tmp_path):
    src1 = _make_source(tmp_path, {"hycommon.log": "one", "other.log": "two"})
    src2 = _make_source(tmp_path, {"hycommon.log": "three"})
    factory = iter([_FakeSSH(src1), _FakeSSH(src2)]).__next__

    out_base = tmp_path / "output"
    ns = "ns1"
    tasks = [
        CollectTask(pod_name="pod1", deploy_name="app", namespace=ns, pattern="*.log"),
        CollectTask(pod_name="pod2", deploy_name="app", namespace=ns, pattern="*.log"),
    ]
    collector = Collector(factory, out_base, max_workers=2)
    results = collector.run(tasks, cancel=Event())
    assert {r.pod_name for r in results} == {"pod1", "pod2"}
    assert all(r.ok for r in results)
    assert (out_base / ns / "app" / "pod1" / "hycommon.log").exists()
    assert (out_base / ns / "app" / "pod2" / "hycommon.log").exists()


def test_collector_no_matching_logs_marked_skipped(tmp_path):
    src = _make_source(tmp_path, {})
    collector = Collector(lambda: _FakeSSH(src), tmp_path / "output", max_workers=1)
    task = CollectTask(pod_name="podX", deploy_name="app", namespace="ns", pattern="*.log")
    results = collector.run([task], cancel=Event())
    assert results[0].ok is False
    assert results[0].error == "无匹配日志"


def test_collector_cancel_stops(tmp_path):
    src = _make_source(tmp_path, {"a.log": "x"})
    collector = Collector(lambda: _FakeSSH(src), tmp_path / "output", max_workers=1)
    cancel = Event()
    cancel.set()
    task = CollectTask(pod_name="podX", deploy_name="app", namespace="ns", pattern="*.log")
    results = collector.run([task], cancel=cancel)
    assert results[0].error == "已取消"


def test_collector_ssh_error_returns_error_result(tmp_path):
    def factory():
        raise RuntimeError("连接失败")

    collector = Collector(factory, tmp_path / "output", max_workers=1)
    task = CollectTask(pod_name="podX", deploy_name="app", namespace="ns", pattern="*.log")
    results = collector.run([task], cancel=Event())
    assert results[0].ok is False
    assert "连接失败" in results[0].error


def test_collector_corrupt_tar_cleans_tmp_and_closes(tmp_path):
    fake = _CorruptStreamClient()
    collector = Collector(lambda: fake, tmp_path / "output", max_workers=1)
    task = CollectTask(pod_name="podX", deploy_name="app", namespace="ns", pattern="*.log")
    results = collector.run([task], cancel=Event())
    assert results[0].ok is False
    assert results[0].error != ""
    # 损坏 tar 导致解析失败，_tmp.tar.gz 必须被清理，SSH 连接必须被关闭
    assert not (tmp_path / "output" / "ns" / "app" / "podX" / "_tmp.tar.gz").exists()
    assert fake.closed is True


def test_collector_cancel_fires_on_progress(tmp_path):
    collector = Collector(lambda: None, tmp_path / "output", max_workers=1)
    cancel = Event()
    cancel.set()
    task = CollectTask(pod_name="podX", deploy_name="app", namespace="ns", pattern="*.log")
    progress = []
    results = collector.run([task], on_progress=progress.append, cancel=cancel)
    assert len(progress) == 1
    assert progress[0].error == "已取消"


def test_collector_on_progress_raise_does_not_abort(tmp_path):
    src = _make_source(tmp_path, {"a.log": "x"})
    collector = Collector(lambda: _FakeSSH(src), tmp_path / "output", max_workers=1)
    task = CollectTask(pod_name="podX", deploy_name="app", namespace="ns", pattern="*.log")

    def bad_callback(result):
        raise RuntimeError("UI 崩了")

    results = collector.run([task], on_progress=bad_callback, cancel=Event())
    assert results[0].ok is True


def test_collector_on_progress_fires_per_task(tmp_path):
    src1 = _make_source(tmp_path, {"hycommon.log": "one"})
    src2 = _make_source(tmp_path, {"hycommon.log": "two"})
    factory = iter([_FakeSSH(src1), _FakeSSH(src2)]).__next__
    collector = Collector(factory, tmp_path / "output", max_workers=2)
    tasks = [
        CollectTask(pod_name="pod1", deploy_name="app", namespace="ns", pattern="*.log"),
        CollectTask(pod_name="pod2", deploy_name="app", namespace="ns", pattern="*.log"),
    ]
    progress = []
    collector.run(tasks, on_progress=progress.append, cancel=Event())
    assert len(progress) == 2
    assert {p.pod_name for p in progress} == {"pod1", "pod2"}


def test_write_manifest(tmp_path):
    metas = [PodMeta(name="pod1", namespace="ns1", deploy_name="app",
                     labels={"project": "p1"},
                     full_json={"spec": {"containers": []}})]
    results = [CollectResult(pod_name="pod1", ok=True, file_count=2)]
    path = tmp_path / "pods_manifest.json"
    write_manifest(path, "ns1", metas, results)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["namespace"] == "ns1"
    assert data["pods"][0]["deployName"] == "app"


def test_zip_output_contains_manifest(tmp_path):
    base = tmp_path / "output"
    date_dir = base / "2026-08-08"
    date_dir.mkdir(parents=True)
    (date_dir / "manifest.json").write_text("{}", encoding="utf-8")
    z = zip_output(base, "2026-08-08", "ns1", "hycommon")
    assert z.exists()
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        assert any(n.endswith("manifest.json") for n in names)


def _make_pod_tree(root: Path, pods: dict) -> Path:
    """按采集输出布局建目录：root/ns/app/<pod>/<file>。"""
    for pod, files in pods.items():
        d = root / "ns" / "app" / pod
        d.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (d / name).write_text(content, encoding="utf-8")
    return root


def test_aggregate_logs_flattens_and_renames(tmp_path):
    source = _make_pod_tree(tmp_path, {
        "podA": {"hycommon.log": "one", "err.log": "two"},
        "podB": {"hycommon.log": "three"},
    })
    dest = tmp_path / "agg"
    stats = aggregate_logs(source, dest)
    assert stats["files"] == 3
    assert stats["errors"] == 0
    assert (dest / "podA_hycommon.log").read_text() == "one"
    assert (dest / "podA_err.log").read_text() == "two"
    assert (dest / "podB_hycommon.log").read_text() == "three"
    assert (source / "ns" / "app" / "podA" / "hycommon.log").exists()  # 源文件保留


def test_aggregate_logs_only_log_files(tmp_path):
    source = _make_pod_tree(tmp_path, {"podA": {"a.log": "x", "a.txt": "y"}})
    (tmp_path / "ns" / "app" / "podA" / "a.tar.gz").write_bytes(b"z")
    stats = aggregate_logs(source, tmp_path / "agg")
    assert stats["files"] == 1
    assert (tmp_path / "agg" / "podA_a.log").exists()
    assert not (tmp_path / "agg" / "podA_a.txt").exists()


def test_aggregate_logs_collision_suffix(tmp_path):
    source = _make_pod_tree(tmp_path / "source", {"podA": {"hycommon.log": "a1"}})
    dest = tmp_path / "agg"
    # 目标目录里预先放一个同名文件，触发 _1 后缀（dest 须在 source 树之外）
    dest.mkdir()
    (dest / "podA_hycommon.log").write_text("old")
    stats = aggregate_logs(source, dest)
    assert stats["files"] == 1
    assert (dest / "podA_hycommon.log").read_text() == "old"      # 原有文件不动
    assert (dest / "podA_hycommon_1.log").read_text() == "a1"     # 新文件加后缀


def test_aggregate_logs_creates_nested_dest(tmp_path):
    source = _make_pod_tree(tmp_path, {"podA": {"hycommon.log": "x"}})
    dest = tmp_path / "logs_collected" / "2026-08-10"
    stats = aggregate_logs(source, dest)
    assert (dest / "podA_hycommon.log").exists()
    assert stats["bytes"] > 0


def test_software_dir_source_returns_project_root():
    root = software_dir()
    assert (root / "main.py").exists()
    assert (root / "src").is_dir()


def test_software_dir_frozen_windows(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(Path, "resolve", lambda self: self)  # 本机非 Windows，避免路径被解析篡改
    monkeypatch.setattr(sys, "executable", "C:/Tools/K8sLogGetter/K8sLogGetter.exe")
    assert software_dir() == Path("C:/Tools/K8sLogGetter")


def test_software_dir_frozen_macos_bundle(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "resolve", lambda self: self)
    exe = "/Users/sunzh/Desktop/K8sLogGetter.app/Contents/MacOS/K8sLogGetter"
    monkeypatch.setattr(sys, "executable", exe)
    assert software_dir() == Path("/Users/sunzh/Desktop")


def test_software_dir_frozen_macos_onefile(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "resolve", lambda self: self)
    exe = "/Users/sunzh/Desktop/k8sgetter"
    monkeypatch.setattr(sys, "executable", exe)
    assert software_dir() == Path("/Users/sunzh/Desktop")
