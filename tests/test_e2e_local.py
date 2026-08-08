# tests/test_e2e_local.py
"""本地端到端：模拟 2 个 Pod 的远端日志目录 → 采集 → manifest → zip。"""
import json
import tarfile
import zipfile
from pathlib import Path
from threading import Event

from src.collector import Collector, write_manifest, zip_output
from src.k8s_client import PATTERN_MAP
from src.models import CollectSummary, CollectTask, PodMeta


class _FakeSSH:
    def __init__(self, source_dir):
        self.source_dir = source_dir

    def stream_to_file(self, command, filepath, timeout=600):
        with tarfile.open(filepath, "w:gz") as tf:
            for p in sorted(self.source_dir.rglob("*")):
                if p.is_file():
                    tf.add(p, arcname=p.relative_to(self.source_dir))
        return 0

    def close(self):
        pass


def test_end_to_end(tmp_path):
    srcs = {}
    for pod, files in {
        "ppl2-a": {"hycommon.log": "one", "hyframework.log": "two"},
        "ppl2-b": {"hycommon.log": "three"},
    }.items():
        d = tmp_path / f"src_{pod}"
        d.mkdir(parents=True)
        for name, content in files.items():
            (d / name).write_text(content, encoding="utf-8")
        srcs[pod] = d

    factory = iter([_FakeSSH(srcs[p]) for p in ("ppl2-a", "ppl2-b")]).__next__
    out_base = tmp_path / "output"
    ns = "3-k251182-default"
    date_name = "2026-08-08"

    tasks = [CollectTask(pod_name=p, deploy_name="ppl2", namespace=ns,
                         pattern=PATTERN_MAP["ALL"]) for p in ("ppl2-a", "ppl2-b")]
    metas = [PodMeta(name=p, namespace=ns, deploy_name="ppl2",
                     labels={"project": "k251182"}) for p in ("ppl2-a", "ppl2-b")]

    # 与真实 UI（collect_page.py）一致：采集器 output_base = <存储目录>/<日期>，
    # 日志落在 <日期>/<命名空间>/<部署名>/<Pod>/，随后整日期目录被打进 zip。
    collect_base = out_base / date_name
    results = Collector(factory, collect_base, max_workers=2).run(tasks, cancel=Event())
    summary = CollectSummary.build(results)
    assert summary.ok == 2

    # write_manifest 不自动建父目录；正常采集已创建日期目录，这里保持防御性 mkdir
    collect_base.mkdir(parents=True, exist_ok=True)
    write_manifest(collect_base / "pods_manifest.json", ns, metas, results)
    manifest = json.loads((collect_base / "pods_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["pods"]) == 2

    # 最终压缩包（含 manifest）应同时包含采集到的日志与 manifest
    z = zip_output(out_base, date_name, ns, "ALL")
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        assert any("ppl2-a/hycommon.log" in n for n in names)
        assert any("pods_manifest.json" in n for n in names)

    # 按设计布局，日志在 <存储目录>/<日期>/<命名空间>/<部署名>/<Pod>/
    assert (collect_base / ns / "ppl2" / "ppl2-a" / "hycommon.log").exists()
