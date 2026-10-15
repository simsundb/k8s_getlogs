# tests/test_e2e_local.py
"""本地端到端：模拟 2 个 Pod 的远端日志目录 → 采集 → 收尾汇总 → 只剩 logs_collected/。"""
import json
import tarfile
from pathlib import Path
from threading import Event

from src.collector import Collector, finish_collection
from src.k8s_client import PATTERN_MAP
from src.models import CollectSummary, CollectTask, PodMeta


class _FakeSSH:
    def __init__(self, source_dir):
        self.source_dir = source_dir

    def exec_stdout(self, command, timeout=60):
        """tar 探测统一回「有 tar」。"""
        return 0, "__TAR_OK__\n", ""

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
    # 日志先落在 <日期>/<命名空间>/<部署名>/<Pod>/，收尾时汇总并清掉这层中间目录。
    collect_base = out_base / date_name
    results = Collector(factory, collect_base, max_workers=2).run(tasks, cancel=Event())
    summary = CollectSummary.build(results)
    assert summary.ok == 2

    # 收尾：汇总 + 写 manifest + 删中间目录树（不再打 zip）
    agg_dir = out_base / "logs_collected" / date_name
    agg = finish_collection(collect_base, agg_dir, ns, metas, results)
    assert agg["files"] == 3
    assert agg["errors"] == 0

    # 最终只剩一个文件夹：日志打平成 <部署名>_<文件名>，manifest 与来源清单一并落在里面
    assert (agg_dir / "ppl2_hycommon.log").read_text(encoding="utf-8") == "one"
    assert (agg_dir / "ppl2_hyframework.log").exists()
    assert (agg_dir / "ppl2_hycommon_1.log").read_text(encoding="utf-8") == "three"
    manifest = json.loads((agg_dir / "pods_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["pods"]) == 2
    copy_log = (agg_dir / "_copy_log.txt").read_text(encoding="utf-8")
    assert "ppl2_hycommon.log" in copy_log
    assert "成功: 3 | 失败: 0" in copy_log

    # 中间目录树与压缩包都不该留下
    assert not collect_base.exists()
    assert list(out_base.rglob("*.zip")) == []
    assert sorted(p.name for p in out_base.iterdir()) == ["logs_collected"]
