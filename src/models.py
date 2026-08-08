from dataclasses import dataclass, field
from typing import Dict, List

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
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
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
    error: str = ""

@dataclass
class CollectSummary:
    total: int = 0
    ok: int = 0
    skipped: int = 0
    failed: int = 0
    results: List[CollectResult] = field(default_factory=list)

    @classmethod
    def build(cls, results: List[CollectResult]) -> "CollectSummary":
        s = cls(total=len(results), results=results)
        for r in results:
            if r.ok:
                s.ok += 1
            elif r.error == "无匹配日志":
                s.skipped += 1
            else:
                s.failed += 1
        return s
