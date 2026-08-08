"""kubectl 命令封装：命名空间、Pod 元数据、tar 流式拉日志。"""
import json
import tarfile
from pathlib import Path

from .models import PodMeta

PATTERN_MAP = {
    "ALL": "*.log",
    "hycommon": "hycommon*.log",
    "hyframework": "hyframework*.log",
}


def list_namespaces(client) -> list[str]:
    code, out, err = client.exec_stdout("kubectl get namespaces -o name")
    if code != 0:
        raise RuntimeError(f"kubectl get namespaces 失败: {err.strip()}")
    return [line.split("/")[-1] for line in out.splitlines() if line.strip()]


def parse_pods_json(raw: str) -> list[PodMeta]:
    data = json.loads(raw)
    metas = []
    for item in data.get("items", []):
        meta = item.get("metadata", {})
        annotations = meta.get("annotations", {}) or {}
        labels = meta.get("labels", {}) or {}
        name = meta.get("name", "")
        deploy = annotations.get("deployName") or name
        status = item.get("status", {})
        restart = sum(cs.get("restartCount", 0) for cs in status.get("containerStatuses", []))
        spec = item.get("spec", {})
        metas.append(PodMeta(
            name=name,
            namespace=meta.get("namespace", ""),
            deploy_name=deploy,
            node=spec.get("nodeName", ""),
            start_time=status.get("startTime", ""),
            pod_ip=status.get("podIP", ""),
            restart_count=restart,
            status=status.get("phase", ""),
            labels=labels,
            annotations=annotations,
            full_json=item,
        ))
    return metas


def get_pods_meta(client, namespace: str) -> list[PodMeta]:
    cmd = f"kubectl get pods -n {namespace} -o json"
    code, out, err = client.exec_stdout(cmd)
    if code != 0:
        raise RuntimeError(f"{cmd} 失败: {err.strip()}")
    return parse_pods_json(out)


def build_tar_command(namespace: str, pod: str, pattern: str) -> str:
    return f"kubectl exec -n {namespace} {pod} -- sh -c 'cd /opt/logs && tar czf - {pattern}'"


def count_tar_files(tar_path: Path) -> int:
    with tarfile.open(tar_path, "r:gz") as tf:
        return sum(1 for m in tf.getmembers() if m.isreg())


def collect_pod_tar(client, namespace: str, pod: str, pattern: str, target_path: Path) -> int:
    """流式下载 Pod 日志 tar 到 target_path，返回日志文件数。失败抛 RuntimeError。"""
    cmd = build_tar_command(namespace, pod, pattern)
    code = client.stream_to_file(cmd, target_path)
    if code != 0:
        target_path.unlink(missing_ok=True)  # 清理失败残留的半成品 tar
        raise RuntimeError(f"tar 拉取失败(exit={code})")
    if target_path.stat().st_size == 0:
        return 0
    return count_tar_files(target_path)
