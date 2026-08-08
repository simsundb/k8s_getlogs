"""kubectl 命令封装：命名空间、Pod 元数据、tar 流式拉日志。"""
import json
import re
import tarfile
from pathlib import Path

from .models import DEFAULT_LOG_DIR, PodMeta

PATTERN_MAP = {
    "ALL": "*.log",
    "hycommon": "hycommon*.log",
    "hyframework": "hyframework*.log",
}


def _sanitize_shell_word(value: str) -> str:
    """只保留路径/文件名的安全字符，防日志目录/日志名注入远端 sh -c 命令。"""
    return re.sub(r"[^A-Za-z0-9._/-]", "", value)


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


def build_log_pattern(category: str, name_filter: str = "") -> str:
    """日志类别 + 可选日志名 → 远端 tar 通配符。

    日志名非空时匹配「包含该名的 .log」（*<名>*.log）；否则用类别预置模式。
    日志名仅保留安全字符，避免被远端 sh 解释成命令/管道。
    """
    name = _sanitize_shell_word(name_filter).strip()
    if name:
        return f"*{name}*.log"
    return PATTERN_MAP.get(category, PATTERN_MAP["ALL"])


def build_tar_command(namespace: str, pod: str, pattern: str,
                      log_dir: str = DEFAULT_LOG_DIR) -> str:
    safe_dir = _sanitize_shell_word(log_dir).strip() or DEFAULT_LOG_DIR
    return (f"kubectl exec -n {namespace} {pod} -- "
            f"sh -c 'cd {safe_dir} && tar czf - {pattern}'")


def count_tar_files(tar_path: Path) -> int:
    with tarfile.open(tar_path, "r:gz") as tf:
        return sum(1 for m in tf.getmembers() if m.isreg())


def collect_pod_tar(client, namespace: str, pod: str, pattern: str,
                    target_path: Path, log_dir: str = DEFAULT_LOG_DIR) -> int:
    """流式下载 Pod 日志 tar 到 target_path，返回日志文件数。失败抛 RuntimeError。"""
    cmd = build_tar_command(namespace, pod, pattern, log_dir)
    code = client.stream_to_file(cmd, target_path)
    if code != 0:
        target_path.unlink(missing_ok=True)  # 清理失败残留的半成品 tar
        stderr = getattr(client, "last_stderr", "").strip()
        raise RuntimeError(f"tar 拉取失败(exit={code}): {cmd}" + (f" | {stderr}" if stderr else ""))
    if target_path.stat().st_size == 0:
        return 0
    return count_tar_files(target_path)
