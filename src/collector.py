"""并发采集器：任务队列 + 线程池 + 输出布局 + manifest + zip。"""
import json
import logging
import tarfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Event

from .k8s_client import collect_pod_tar
from .models import NO_MATCH_ERROR, CollectResult, CollectTask, PodMeta

log = logging.getLogger("collector")


def extract_tar(tar_path: Path, dest_dir: Path) -> int:
    """把 tar.gz 解压到 dest_dir，返回其中普通文件数。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(tar_path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.isreg():
                count += 1
        tf.extractall(dest_dir)
    return count


def write_manifest(path: Path, namespace: str, metas: list[PodMeta], results: list[CollectResult]) -> None:
    """写 pods_manifest.json：Pod 摘要 + 采集状态。结果按 pod_name 关联。"""
    result_map = {r.pod_name: r for r in results}
    pods = []
    for pm in metas:
        r = result_map.get(pm.name)
        entry = pm.summary()
        entry["collected"] = r.ok if r else False
        entry["fileCount"] = r.file_count if r else 0
        entry["fullJson"] = pm.full_json
        pods.append(entry)
    data = {
        "collectedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "namespace": namespace,
        "pods": pods,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def zip_output(output_base: Path, date_dir_name: str, namespace: str, category: str) -> Path:
    """把 <output_base>/<date_dir_name> 打成 <output_base>/<date>-<ns>-<category>.zip，返回 zip 路径。"""
    source = output_base / date_dir_name
    target = output_base / f"{date_dir_name}-{namespace}-{category}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(output_base))
    return target


class Collector:
    """并发采集器：每个任务独立创建 SSH 连接，线程池并行拉取日志。"""

    def __init__(self, ssh_factory, output_base: Path, max_workers: int = 4):
        self.ssh_factory = ssh_factory
        self.output_base = output_base
        self.max_workers = max_workers

    def run(self, tasks: list[CollectTask], on_progress=None, cancel: Event = None) -> list[CollectResult]:
        """并行执行所有任务。on_progress 在工作线程内回调，UI 层需自行 marshaling 到主线程。"""
        cancel = cancel or Event()

        def worker(task: CollectTask) -> CollectResult:
            if cancel.is_set():
                return CollectResult(task.pod_name, False, error="已取消")
            client = None
            try:
                client = self.ssh_factory()
                target_dir = self.output_base / task.namespace / task.deploy_name / task.pod_name
                target_dir.mkdir(parents=True, exist_ok=True)
                tar_path = target_dir / "_tmp.tar.gz"
                count = collect_pod_tar(client, task.namespace, task.pod_name, task.pattern, tar_path)
                if count == 0:
                    tar_path.unlink(missing_ok=True)
                    result = CollectResult(task.pod_name, False, error=NO_MATCH_ERROR)
                else:
                    extract_tar(tar_path, target_dir)
                    tar_path.unlink(missing_ok=True)
                    result = CollectResult(task.pod_name, True, file_count=count)
            except Exception as e:
                log.warning("Pod %s 采集失败: %s", task.pod_name, e)
                result = CollectResult(task.pod_name, False, error=str(e))
            finally:
                if client:
                    client.close()
            if on_progress:
                on_progress(result)
            return result

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            results = list(pool.map(worker, tasks))
        return results
