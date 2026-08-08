"""K8S 日志采集工具共享数据模型。"""

from dataclasses import dataclass, field

NO_MATCH_ERROR = "无匹配日志"


@dataclass
class HostConfig:
    ip: str
    username: str
    password: str = ""
    port: int = 22
    remark: str = ""


@dataclass
class PodMeta:
    name: str
    namespace: str
    deploy_name: str
    node: str = ""
    start_time: str = ""
    pod_ip: str = ""
    restart_count: int = 0
    status: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    full_json: dict = field(default_factory=dict)

    def summary(self) -> dict:
        containers = self.full_json.get("spec", {}).get("containers", [])
        image = containers[0].get("image", "") if containers else ""
        return {
            "pod": self.name,
            "deployName": self.deploy_name,
            "project": self.labels.get("project", ""),
            "image": image,
            "node": self.node,
            "startTime": self.start_time,
            "podIP": self.pod_ip,
            "restartCount": self.restart_count,
        }


@dataclass
class CollectTask:
    pod_name: str
    deploy_name: str
    namespace: str
    pattern: str


@dataclass
class CollectResult:
    pod_name: str
    ok: bool
    file_count: int = 0
    total_bytes: int = 0
    error: str = ""


@dataclass
class CollectSummary:
    total: int = 0
    ok: int = 0
    skipped: int = 0
    failed: int = 0
    total_bytes: int = 0
    results: list[CollectResult] = field(default_factory=list)

    @classmethod
    def build(cls, results: list[CollectResult]) -> "CollectSummary":
        s = cls(total=len(results), results=results)
        for r in results:
            if r.ok:
                s.ok += 1
                s.total_bytes += r.total_bytes
            elif r.error == NO_MATCH_ERROR:
                s.skipped += 1
            else:
                s.failed += 1
        return s


def human_size(num: int) -> str:
    """字节数转人类可读：0 → "0 B"，1536 → "1.5 KB"。"""
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
