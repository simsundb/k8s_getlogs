import json
import tarfile
import zipfile
from pathlib import Path
from threading import Event

from src.collector import Collector, extract_tar, write_manifest, zip_output
from src.models import CollectResult, CollectTask, PodMeta


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


def test_extract_tar(tmp_path):
    src = _make_source(tmp_path, {"a.log": "aaa", "b.log": "bbb"})
    fake = _FakeSSH(src)
    tar = tmp_path / "p.tar.gz"
    fake.stream_to_file("ignored", tar)
    dest = tmp_path / "dest"
    n = extract_tar(tar, dest)
    assert n == 2
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
