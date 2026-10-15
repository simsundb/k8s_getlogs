"""kubectl 命令封装：命名空间、Pod 元数据、tar 流式拉日志（容器无 tar 时降级逐文件读取）。"""
import json
import logging
import re
import tarfile
from pathlib import Path

from .models import DEFAULT_LOG_DIR, PodMeta

log = logging.getLogger("k8s_client")

PATTERN_MAP = {
    "ALL": "*.log",
    "hycommon": "hycommon*.log",
    "hyframework": "hyframework*.log",
}

# 容器内 tar 探测标记：回显即说明有 tar，可走 tar 流式打包
TAR_PROBE_MARK = "__TAR_OK__"
# 降级流（容器无 tar）的文件头前缀：「L:<相对路径>\n<字节数>\n<正文…>」
STREAM_HEAD = "L:"
_STREAM_HEAD_B = STREAM_HEAD.encode()  # 本地按字节解析共用同一前缀


def _sanitize_shell_word(value: str) -> str:
    """只保留路径/文件名的安全字符，防日志目录/日志名注入远端 sh -c 命令。"""
    return re.sub(r"[^A-Za-z0-9._/-]", "", value)


def _sanitize_glob(value: str) -> str:
    """通配符专用清洗：在 _sanitize_shell_word 基础上放行 *，其余元字符照旧剔除。"""
    return re.sub(r"[^A-Za-z0-9._/*-]", "", value)


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
            f"sh -c 'cd {safe_dir} && tar czf - {_sanitize_glob(pattern)}'")


def count_tar_files(tar_path: Path) -> int:
    with tarfile.open(tar_path, "r:gz") as tf:
        return sum(1 for m in tf.getmembers() if m.isreg())


def has_tar_command(client, namespace: str, pod: str) -> bool:
    """探测容器内有没有 tar 命令（依赖容器内有 sh）。

    有 tar → True；没 tar / 没 sh / exec 返回非 0 → False，调用方改走降级路径。
    探测本身抛出的连接层异常不吞，直接上抛，由采集器记为该 Pod 的失败原因。
    """
    cmd = (f"kubectl exec -n {namespace} {pod} -- "
           f"sh -c 'command -v tar >/dev/null 2>&1 && echo {TAR_PROBE_MARK}'")
    code, out, _ = client.exec_stdout(cmd, timeout=30)
    return code == 0 and TAR_PROBE_MARK in out


def build_cat_command(namespace: str, pod: str, pattern: str,
                      log_dir: str = DEFAULT_LOG_DIR) -> str:
    """无 tar 容器的降级命令：逐文件输出「L:<路径>\\n<字节数>\\n<正文>」。

    头部用换行分隔、正文由调用方按声明的字节数精确读取，因此正文里出现 "L:"
    也不会被误判成下一个文件头。只收普通文件（`[ -f ]`），匹配不到时循环体不执行
    （等价于 0 个日志），不像 tar 那样因通配符无匹配而报错退出。
    """
    safe_dir = _sanitize_shell_word(log_dir).strip() or DEFAULT_LOG_DIR
    safe_pattern = _sanitize_glob(pattern)
    script = (
        f"cd {safe_dir} || exit 1; "
        f'for f in {safe_pattern}; do [ -f "$f" ] || continue; '
        f'printf "{STREAM_HEAD}%s\\n" "$f"; wc -c < "./$f"; cat "./$f"; done'
    )
    return f"kubectl exec -n {namespace} {pod} -- sh -c '{script}'"


def pack_stream_to_tar(raw_path: Path, tar_path: Path) -> int:
    """把降级流重新打成 tar.gz（成员名 = 流里的相对路径），返回日志文件数。

    边读边写：正文交给 tarfile 按 size 精确搬运，整包日志不会读进内存。
    容器侧 cat 中断导致正文短于声明、或头部格式不对时抛 RuntimeError，
    并删掉半成品 tar，避免下游把残缺包当成采集成功。
    """
    count = 0
    total = raw_path.stat().st_size
    try:
        with open(raw_path, "rb") as fh, tarfile.open(tar_path, "w:gz") as tf:
            while True:
                head = fh.readline()
                if not head:
                    break
                if not head.startswith(_STREAM_HEAD_B):
                    raise RuntimeError(f"降级流格式异常: {head[:80]!r}")
                name = head[len(_STREAM_HEAD_B):].decode("utf-8", "replace").rstrip("\n")
                size_line = fh.readline()
                try:
                    size = int(size_line.strip())
                except ValueError:
                    raise RuntimeError(f"降级流缺少文件长度: {size_line[:80]!r}") from None
                left = total - fh.tell()
                if size < 0 or size > left:
                    raise RuntimeError(
                        f"降级流被截断: {name} 声明 {size} 字节，实际只剩 {left} 字节")
                info = tarfile.TarInfo(name)
                info.size = size
                tf.addfile(info, fh)
                count += 1
    except BaseException:
        tar_path.unlink(missing_ok=True)
        raise
    return count


def collect_pod_logs(client, namespace: str, pod: str, pattern: str,
                     target_path: Path, log_dir: str = DEFAULT_LOG_DIR) -> int:
    """拉取 Pod 内匹配 pattern 的日志到 target_path（tar.gz），返回日志文件数。

    容器有 tar 就流式下载 tar 包；没有则退回逐文件读取、在本地重新打包成同样的
    tar.gz。两条路径产出的 target_path 结构一致，下游解压/加前缀/汇总逻辑无需区分。
    失败抛 RuntimeError。
    """
    if has_tar_command(client, namespace, pod):
        cmd = build_tar_command(namespace, pod, pattern, log_dir)
        code = client.stream_to_file(cmd, target_path)
        if code != 0:
            target_path.unlink(missing_ok=True)  # 清理失败残留的半成品 tar
            stderr = getattr(client, "last_stderr", "").strip()
            raise RuntimeError(f"tar 拉取失败(exit={code}): {cmd}" + (f" | {stderr}" if stderr else ""))
        if target_path.stat().st_size == 0:
            return 0
        return count_tar_files(target_path)

    log.info("Pod %s/%s 容器内无 tar 命令，改用逐文件读取降级采集", namespace, pod)
    # 降级流先落临时文件（stream_to_file 只能写文件），再本地重新打包成 tar.gz
    raw_path = target_path.parent / f"{target_path.name}.raw"
    try:
        cmd = build_cat_command(namespace, pod, pattern, log_dir)
        code = client.stream_to_file(cmd, raw_path)
        if code != 0:
            stderr = getattr(client, "last_stderr", "").strip()
            raise RuntimeError(f"日志拉取失败(exit={code}): {cmd}" + (f" | {stderr}" if stderr else ""))
        return pack_stream_to_tar(raw_path, target_path)
    finally:
        raw_path.unlink(missing_ok=True)
