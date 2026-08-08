# K8S 日志采集与分析工具 —— 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 PySide6 + paramiko 构建三页面 K8S 日志工具：SSH 主机配置、日志抓取（tar 流式 + 并发打包）、Pod 元数据查询分析。

**Architecture:** 后端（models/config/ssh/k8s/collector）与 UI 分离。页面②③共用 `HostNamespaceSelector`（选主机→自动连→命名空间下拉）。采集走任务队列 + 4 线程并发，每 worker 独立 SSH 连接；输出按部署名分组 + manifest + zip。

**Tech Stack:** Python 3.12、PySide6、paramiko、pytest。跨平台 Windows/macOS，路径用 `pathlib`。

**Spec:** `docs/superpowers/specs/2026-08-08-k8s-log-getter-design.md`

**约定：**
- 所有命令在项目根目录 `D:\claude.ai\k8s_getlogs` 运行
- 测试用 `python -m pytest tests/... -v`（Windows 下 `python -m pytest` 更稳）
- UI 测试用 offscreen 平台（无需显示器），Windows/macOS 均支持

---

## 文件结构

```
main.py                    # 入口：初始化日志 + 启动 QApplication
pyproject.toml             # 依赖 + pytest 配置
requirements.txt           # 运行依赖
src/
  __init__.py
  config.py                # 配置读写 + base64 密码编解码
  logger.py                # 日志初始化（RotatingFileHandler）
  models.py                # 数据类：HostConfig / PodMeta / CollectTask / CollectResult
  ssh_client.py            # paramiko 封装：连接 / exec_stdout / stream_to_file
  k8s_client.py            # kubectl 封装：命名空间 / Pod元数据 / tar 拉日志 / pattern映射
  collector.py             # 线程池并发采集 + 输出布局 + manifest + zip
  ui/
    __init__.py
    log_panel.py           # 滚动只读日志面板
    host_ns_selector.py    # 共享组件：主机下拉 + 自动连接 + 命名空间下拉
    host_page.py           # 页面①：主机管理
    collect_page.py        # 页面②：日志抓取
    analyze_page.py        # 页面③：查询分析
    main_window.py         # 主窗口：左侧页签 + QStackedWidget
tests/
  __init__.py
  test_models.py
  test_config.py
  test_logger.py
  test_ssh_client.py
  test_k8s_client.py
  test_collector.py
  test_analyze_filter.py
  test_ui_smoke.py
  test_e2e_local.py
```

---

### Task 1: 项目脚手架

**Files:**
- Create: `requirements.txt`
- Create: `pyproject.toml`
- Create: `src/__init__.py`
- Create: `src/ui/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: 写依赖文件**

`requirements.txt`：
```
PySide6>=6.5.0
paramiko>=3.0.0
```

`pyproject.toml`：
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 2: 创建包目录**

运行：
```bash
mkdir -p src/ui tests
touch src/__init__.py src/ui/__init__.py tests/__init__.py
```

- [ ] **Step 3: 安装依赖**

运行：
```bash
python -m pip install -r requirements.txt pytest
```
预期：安装成功，无报错。

- [ ] **Step 4: 验证 pytest 可运行**

运行：`python -m pytest -v`
预期：`no tests ran`，退出码 0（集合成功）。

- [ ] **Step 5: Commit**

```bash
git add requirements.txt pyproject.toml src/__init__.py src/ui/__init__.py tests/__init__.py
git commit -m "chore: 项目脚手架与依赖"
```

---

### Task 2: 软件自身日志（src/logger.py）

**Files:**
- Create: `src/logger.py`
- Test: `tests/test_logger.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_logger.py
import logging
from pathlib import Path

def _fresh(monkeypatch):
    import src.logger as L
    monkeypatch.setattr(L, "_configured", False)
    return L

def test_logger_writes_to_file(tmp_path, monkeypatch):
    L = _fresh(monkeypatch)
    log_dir = tmp_path / "logs"
    log_file = L.setup_logging(log_dir)
    assert log_file.name == "app.log"
    logging.getLogger("test").info("hello-123")
    assert log_file.exists()
    assert "hello-123" in log_file.read_text(encoding="utf-8")

def test_setup_idempotent_no_duplicate_handlers(tmp_path, monkeypatch):
    L = _fresh(monkeypatch)
    L.setup_logging(tmp_path)
    before = len(logging.getLogger().handlers)
    L.setup_logging(tmp_path)
    assert len(logging.getLogger().handlers) == before
```

- [ ] **Step 2: 运行确认失败**

运行：`python -m pytest tests/test_logger.py -v`
预期：`ModuleNotFoundError: No module named 'src.logger'`

- [ ] **Step 3: 最小实现**

```python
# src/logger.py
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_configured = False

def setup_logging(log_dir: Path) -> Path:
    """初始化根 logger：文件轮转 + 控制台。返回日志文件路径。"""
    global _configured
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    if _configured:
        return log_file
    root.setLevel(logging.DEBUG)
    fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)
    root.addHandler(ch)
    _configured = True
    return log_file
```

- [ ] **Step 4: 运行确认通过**

运行：`python -m pytest tests/test_logger.py -v`
预期：2 passed

- [ ] **Step 5: Commit**

```bash
git add src/logger.py tests/test_logger.py
git commit -m "feat: 软件自身日志（轮转+控制台）"
```

---

### Task 3: 数据模型（src/models.py）

**Files:**
- Create: `src/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_models.py
from src.models import CollectResult, PodMeta

def test_podmeta_summary_extracts_key_fields():
    pm = PodMeta(
        name="ppl2-abc",
        namespace="3-k251182-default",
        deploy_name="gbc-ai-assistant-service",
        node="node-k251182-15f12e",
        start_time="2026-08-07 23:34:46 +0800",
        pod_ip="10.244.20.85",
        restart_count=3,
        labels={"project": "k251182"},
        full_json={"spec": {"containers": [{"image": "devops.harbor.cn:8443/x/app:1.0.0"}]}},
    )
    s = pm.summary()
    assert s["deployName"] == "gbc-ai-assistant-service"
    assert s["project"] == "k251182"
    assert s["image"] == "devops.harbor.cn:8443/x/app:1.0.0"
    assert s["restartCount"] == 3

def test_collect_result_defaults():
    r = CollectResult(pod_name="p1", ok=True)
    assert r.file_count == 0
    assert r.error == ""
```

- [ ] **Step 2: 运行确认失败**

运行：`python -m pytest tests/test_models.py -v`
预期：`ModuleNotFoundError: No module named 'src.models'`

- [ ] **Step 3: 最小实现**

```python
# src/models.py
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
```

- [ ] **Step 4: 运行确认通过**

运行：`python -m pytest tests/test_models.py -v`
预期：2 passed

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: 数据模型（HostConfig/PodMeta/CollectTask/CollectResult）"
```

---

### Task 4: 配置读写 + base64 密码（src/config.py）

**Files:**
- Create: `src/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config.py
import json

from src.config import (decode_password, encode_password, hosts_from_config,
                        hosts_to_config)
from src.models import HostConfig

def test_password_base64_roundtrip():
    assert decode_password(encode_password("my@Secret!")) == "my@Secret!"

def test_password_not_stored_in_plaintext():
    hosts = [HostConfig(ip="1.2.3.4", username="root", password="secret123")]
    data = hosts_to_config(hosts)
    raw = json.dumps(data)
    assert "secret123" not in raw

def test_hosts_roundtrip():
    hosts = [HostConfig(ip="1.2.3.4", port=22, username="root", password="pw1", remark="dev")]
    back = hosts_from_config(hosts_to_config(hosts))
    assert back[0].ip == "1.2.3.4"
    assert back[0].password == "pw1"
    assert back[0].remark == "dev"

def test_hosts_from_config_skips_broken_entry():
    data = {"hosts": [{"ip": "9.9.9.9", "username": "u", "password_b64": encode_password("x")}, {"bad": 1}]}
    out = hosts_from_config(data)
    assert len(out) == 1
    assert out[0].ip == "9.9.9.9"
```

- [ ] **Step 2: 运行确认失败**

运行：`python -m pytest tests/test_config.py -v`
预期：`ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 3: 最小实现**

```python
# src/config.py
import base64
import json
from pathlib import Path
from typing import Dict, List

from .models import HostConfig

APP_DIR = Path.home() / ".k8s_log_getter"
CONFIG_PATH = APP_DIR / "config.json"


def encode_password(password: str) -> str:
    return base64.b64encode(password.encode("utf-8")).decode("ascii")


def decode_password(encoded: str) -> str:
    return base64.b64decode(encoded.encode("ascii")).decode("utf-8")


def default_config() -> Dict:
    return {"hosts": [], "output_dir": ""}


def load_config() -> Dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return default_config()


def save_config(data: Dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def hosts_from_config(data: Dict) -> List[HostConfig]:
    out = []
    for item in data.get("hosts", []):
        try:
            out.append(HostConfig(
                ip=item["ip"],
                port=int(item.get("port", 22)),
                username=item["username"],
                password=decode_password(item["password_b64"]),
                remark=item.get("remark", ""),
            ))
        except (KeyError, ValueError):
            continue
    return out


def hosts_to_config(hosts: List[HostConfig]) -> list:
    return [{
        "ip": h.ip,
        "port": h.port,
        "username": h.username,
        "password_b64": encode_password(h.password),
        "remark": h.remark,
    } for h in hosts]
```

- [ ] **Step 4: 运行确认通过**

运行：`python -m pytest tests/test_config.py -v`
预期：4 passed

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: 配置读写与base64密码存储"
```

---

### Task 5: SSH 客户端（src/ssh_client.py）

**Files:**
- Create: `src/ssh_client.py`
- Test: `tests/test_ssh_client.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ssh_client.py
from unittest import mock
from pathlib import Path

import pytest

from src.ssh_client import SSHClient


class _FakeChannel:
    def __init__(self, exit_code=0, out="", err=""):
        self._code = exit_code
        self._out = out.encode("utf-8")
        self._err = err.encode("utf-8")
        self._pos = 0

    def recv(self, n):
        chunk = self._out[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk

    def recv_exit_status(self):
        return self._code


class _FakeStdout:
    def __init__(self, code, text):
        self.channel = _FakeChannel(code)
        self._text = text.encode("utf-8")

    def read(self):
        return self._text


class _FakeStderr:
    def __init__(self, text):
        self._text = text.encode("utf-8")

    def read(self):
        return self._text


class _FakeSessionChannel:
    def __init__(self, exec_map):
        self._exec_map = exec_map
        self._stream = b""
        self._code = 0
        self._pos = 0

    def settimeout(self, t):
        pass

    def exec_command(self, command):
        code, out, _ = self._exec_map.get(command, (0, "", ""))
        self._code = code
        self._stream = out.encode("utf-8")

    def recv(self, n):
        chunk = self._stream[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk

    def recv_exit_status(self):
        return self._code


class _FakeClient:
    def __init__(self, exec_map=None):
        self.exec_map = exec_map or {}
        self.transport = _FakeTransport(self.exec_map)

    def exec_command(self, command, timeout=60):
        code, out, err = self.exec_map.get(command, (0, "", ""))
        return None, _FakeStdout(code, out), _FakeStderr(err)


class _FakeTransport:
    def __init__(self, exec_map):
        self._exec_map = exec_map

    def open_session(self):
        return _FakeSessionChannel(self._exec_map)


def _make_client(exec_map=None):
    c = SSHClient("10.0.0.1", 22, "root", "pw")
    c._client = _FakeClient(exec_map)
    return c


def test_exec_stdout_returns_code_out_err():
    c = _make_client({"kubectl get ns": (0, "ns1\nns2\n", "")})
    code, out, err = c.exec_stdout("kubectl get ns")
    assert code == 0
    assert out == "ns1\nns2\n"
    assert err == ""


def test_stream_to_file_writes_bytes(tmp_path):
    payload = "A" * 1000
    c = _make_client({"cmd": (0, payload, "")})
    target = tmp_path / "out.bin"
    code = c.stream_to_file("cmd", str(target))
    assert code == 0
    assert target.read_text() == payload


@mock.patch("src.ssh_client.paramiko.SSHClient")
def test_connect_success(mock_cls):
    mock_client = mock.MagicMock()
    mock_cls.return_value = mock_client
    c = SSHClient("10.0.0.1", 22, "root", "pw").connect()
    mock_client.connect.assert_called_once()
    assert c._client is mock_client


@mock.patch("src.ssh_client.paramiko.SSHClient")
def test_connect_failure_raises(mock_cls):
    mock_client = mock.MagicMock()
    mock_client.connect.side_effect = Exception("auth failed")
    mock_cls.return_value = mock_client
    with pytest.raises(Exception):
        SSHClient("10.0.0.1", 22, "root", "pw").connect()
```

> 注：`stream_to_file` 里 `open(filepath, "wb")` 接受 `Path`，测试传 `str` 亦可，实现统一用 `Path`。测试中的 `str(target)` 与实现 `open(filepath, ...)` 兼容。

- [ ] **Step 2: 运行确认失败**

运行：`python -m pytest tests/test_ssh_client.py -v`
预期：`ModuleNotFoundError: No module named 'src.ssh_client'`

- [ ] **Step 3: 最小实现**

```python
# src/ssh_client.py
from pathlib import Path
from typing import Optional, Tuple

import paramiko


class SSHClient:
    """paramiko 封装：连接、一次性读小输出、流式写大输出到文件。"""

    def __init__(self, host: str, port: int, username: str, password: str, timeout: int = 15):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self._client: Optional[paramiko.SSHClient] = None

    def connect(self) -> "SSHClient":
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host, port=self.port,
            username=self.username, password=self.password,
            timeout=self.timeout, allow_agent=False, look_for_keys=False,
        )
        self._client = client
        return self

    def exec_stdout(self, command: str, timeout: int = 60) -> Tuple[int, str, str]:
        """执行命令，一次性读回 (退出码, stdout, stderr)。适合小输出。"""
        stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return stdout.channel.recv_exit_status(), out, err

    def stream_to_file(self, command: str, filepath: Path, timeout: int = 600) -> int:
        """执行命令，把 stdout 流式写入文件，返回退出码。适合 tar 等大输出。"""
        channel = self._client.get_transport().open_session()
        channel.settimeout(timeout)
        channel.exec_command(command)
        with open(filepath, "wb") as fh:
            while True:
                chunk = channel.recv(65536)
                if not chunk:
                    break
                fh.write(chunk)
        return channel.recv_exit_status()

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
```

- [ ] **Step 4: 运行确认通过**

运行：`python -m pytest tests/test_ssh_client.py -v`
预期：5 passed

- [ ] **Step 5: Commit**

```bash
git add src/ssh_client.py tests/test_ssh_client.py
git commit -m "feat: SSH客户端（连接/exec/流式下载）"
```

---

### Task 6: kubectl 封装（src/k8s_client.py）

**Files:**
- Create: `src/k8s_client.py`
- Test: `tests/test_k8s_client.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_k8s_client.py
import io
import json
import tarfile

import pytest

from src.k8s_client import (PATTERN_MAP, build_tar_command, count_tar_files,
                            list_namespaces, parse_pods_json)


class _FakeClient:
    def __init__(self, result):
        self._result = result

    def exec_stdout(self, cmd, timeout=60):
        return self._result


def test_pattern_map_matches_spec():
    assert PATTERN_MAP["ALL"] == "*.log"
    assert PATTERN_MAP["hycommon"] == "hycommon*.log"
    assert PATTERN_MAP["hyframework"] == "hyframework*.log"


def test_list_namespaces_ok():
    c = _FakeClient((0, "namespace/ns1\nnamespace/ns2\n", ""))
    assert list_namespaces(c) == ["ns1", "ns2"]


def test_list_namespaces_failure_raises():
    c = _FakeClient((1, "", "error: no server"))
    with pytest.raises(RuntimeError):
        list_namespaces(c)


def test_parse_pods_json_deploy_fallback_and_restart_sum():
    raw = json.dumps({"items": [
        {
            "metadata": {
                "name": "app-1-abc",
                "namespace": "ns1",
                "labels": {"project": "p1"},
                "annotations": {"deployName": "app"},
            },
            "spec": {"nodeName": "node1"},
            "status": {
                "phase": "Running",
                "podIP": "10.0.0.1",
                "startTime": "2026-08-07T00:00:00Z",
                "containerStatuses": [{"restartCount": 2}, {"restartCount": 1}],
            },
        },
        {
            "metadata": {"name": "ds-2-xyz", "namespace": "ns1", "annotations": {}},
            "spec": {"nodeName": "node2"},
            "status": {"phase": "Pending", "containerStatuses": []},
        },
    ]})
    metas = parse_pods_json(raw)
    assert metas[0].deploy_name == "app"
    assert metas[0].restart_count == 3
    assert metas[0].status == "Running"
    assert metas[0].labels["project"] == "p1"
    assert metas[1].deploy_name == "ds-2-xyz"   # 注解缺失回退 Pod 名
    assert metas[1].restart_count == 0


def test_build_tar_command():
    cmd = build_tar_command("ns1", "pod1", "hycommon*.log")
    assert "kubectl exec -n ns1 pod1" in cmd
    assert "cd /opt/logs" in cmd
    assert "hycommon*.log" in cmd


def test_count_tar_files(tmp_path):
    p = tmp_path / "t.tgz"
    with tarfile.open(p, "w:gz") as tf:
        for name in ("a.log", "b.log", "sub/c.log"):
            info = tarfile.TarInfo(name)
            info.size = 3
            tf.addfile(info, io.BytesIO(b"abc"))
    assert count_tar_files(p) == 3
```

- [ ] **Step 2: 运行确认失败**

运行：`python -m pytest tests/test_k8s_client.py -v`
预期：`ModuleNotFoundError: No module named 'src.k8s_client'`

- [ ] **Step 3: 最小实现**

```python
# src/k8s_client.py
import json
import tarfile
from pathlib import Path
from typing import List

from .models import PodMeta

PATTERN_MAP = {
    "ALL": "*.log",
    "hycommon": "hycommon*.log",
    "hyframework": "hyframework*.log",
}


def list_namespaces(client) -> List[str]:
    code, out, err = client.exec_stdout("kubectl get namespaces -o name")
    if code != 0:
        raise RuntimeError(f"kubectl get namespaces 失败: {err.strip()}")
    return [line.split("/")[-1] for line in out.splitlines() if line.strip()]


def parse_pods_json(raw: str) -> List[PodMeta]:
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


def get_pods_meta(client, namespace: str) -> List[PodMeta]:
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
        raise RuntimeError(f"tar 拉取失败(exit={code})")
    if target_path.stat().st_size == 0:
        return 0
    return count_tar_files(target_path)
```

- [ ] **Step 4: 运行确认通过**

运行：`python -m pytest tests/test_k8s_client.py -v`
预期：6 passed

- [ ] **Step 5: Commit**

```bash
git add src/k8s_client.py tests/test_k8s_client.py
git commit -m "feat: kubectl封装（命名空间/Pod元数据/tar拉取/pattern映射）"
```

---

### Task 7: 并发采集 + 输出布局 + manifest + zip（src/collector.py）

**Files:**
- Create: `src/collector.py`
- Test: `tests/test_collector.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_collector.py
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


def test_collector_cancel_stops():
    src = _make_source(tmp_path, {"a.log": "x"})
    collector = Collector(lambda: _FakeSSH(src), tmp_path / "output", max_workers=1)
    cancel = Event()
    cancel.set()
    task = CollectTask(pod_name="podX", deploy_name="app", namespace="ns", pattern="*.log")
    results = collector.run([task], cancel=cancel)
    assert results[0].error == "已取消"


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
```

- [ ] **Step 2: 运行确认失败**

运行：`python -m pytest tests/test_collector.py -v`
预期：`ModuleNotFoundError: No module named 'src.collector'`

- [ ] **Step 3: 最小实现**

```python
# src/collector.py
import json
import logging
import tarfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Callable, List

from .k8s_client import collect_pod_tar
from .models import CollectResult, CollectSummary, CollectTask, PodMeta

log = logging.getLogger("collector")


def extract_tar(tar_path: Path, dest_dir: Path) -> int:
    dest_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(tar_path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.isreg():
                count += 1
        tf.extractall(dest_dir)
    return count


def write_manifest(path: Path, namespace: str, metas: List[PodMeta], results: List[CollectResult]) -> None:
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
    source = output_base / date_dir_name
    target = output_base / f"{date_dir_name}-{namespace}-{category}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(output_base))
    return target


class Collector:
    def __init__(self, ssh_factory: Callable, output_base: Path, max_workers: int = 4):
        self.ssh_factory = ssh_factory
        self.output_base = output_base
        self.max_workers = max_workers

    def run(self, tasks: List[CollectTask], on_progress=None, cancel: Event = None) -> List[CollectResult]:
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
                    result = CollectResult(task.pod_name, False, error="无匹配日志")
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
```

- [ ] **Step 4: 运行确认通过**

运行：`python -m pytest tests/test_collector.py -v`
预期：6 passed

- [ ] **Step 5: Commit**

```bash
git add src/collector.py tests/test_collector.py
git commit -m "feat: 并发采集器（tar流式+线程池+manifest+zip）"
```

---

### Task 8: 日志面板（src/ui/log_panel.py）

**Files:**
- Create: `src/ui/log_panel.py`

- [ ] **Step 1: 实现**

```python
# src/ui/log_panel.py
from PySide6.QtWidgets import QPlainTextEdit


class LogPanel(QPlainTextEdit):
    """只读滚动日志面板，自动滚到底部，限制最大行数防内存暴涨。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)

    def append_log(self, text: str) -> None:
        self.appendPlainText(text)
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear_log(self) -> None:
        self.clear()
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/log_panel.py
git commit -m "feat: 日志面板组件"
```

---

### Task 9: 共享组件 HostNamespaceSelector（src/ui/host_ns_selector.py）

**Files:**
- Create: `src/ui/host_ns_selector.py`

- [ ] **Step 1: 实现**

```python
# src/ui/host_ns_selector.py
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton,
                               QWidget)

from ..k8s_client import list_namespaces
from ..models import HostConfig
from ..ssh_client import SSHClient


class HostNamespaceSelector(QWidget):
    """选主机 → 自动连接 → 命名空间下拉。页面②③共用。"""
    connected = Signal(object)        # SSHClient
    namespacesLoaded = Signal(list)   # list[str]
    connectionFailed = Signal(str)
    disconnected = Signal()

    def __init__(self, hosts_provider, parent=None):
        super().__init__(parent)
        self.hosts_provider = hosts_provider
        self._client = None
        self._populating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("SSH主机:"))
        self.host_combo = QComboBox()
        self.host_combo.setMinimumWidth(200)
        layout.addWidget(self.host_combo)
        self.connect_btn = QPushButton("连接")
        layout.addWidget(self.connect_btn)
        layout.addSpacing(16)
        layout.addWidget(QLabel("命名空间:"))
        self.ns_combo = QComboBox()
        self.ns_combo.setMinimumWidth(220)
        layout.addWidget(self.ns_combo)
        self.refresh_btn = QPushButton("刷新")
        layout.addWidget(self.refresh_btn)
        layout.addStretch(1)

        self.connect_btn.clicked.connect(self.connect_now)
        self.refresh_btn.clicked.connect(self.refresh_namespaces)
        self.host_combo.currentIndexChanged.connect(self._on_host_changed)

    def refresh_hosts(self):
        self._populating = True
        try:
            self.host_combo.clear()
            for h in self.hosts_provider():
                self.host_combo.addItem(f"{h.ip}:{h.port} ({h.username})", h)
        finally:
            self._populating = False
        if self.host_combo.count():
            self.host_combo.setCurrentIndex(0)

    def current_host(self) -> HostConfig:
        return self.host_combo.currentData()

    def client(self) -> SSHClient:
        return self._client

    def connect_now(self):
        host = self.current_host()
        if host is None:
            self.connectionFailed.emit("请先在「主机配置」页添加主机")
            return
        try:
            client = SSHClient(host.ip, host.port, host.username, host.password).connect()
        except Exception as e:
            self.connectionFailed.emit(f"连接 {host.ip} 失败: {e}")
            return
        if self._client:
            self._client.close()
        self._client = client
        self.connected.emit(client)
        self.refresh_namespaces()

    def _on_host_changed(self, index):
        if self._populating:
            return
        if self._client:
            self._client.close()
            self._client = None
            self.disconnected.emit()
        self.ns_combo.clear()
        if self.host_combo.count() and index >= 0:
            self.connect_now()

    def refresh_namespaces(self):
        if not self._client:
            self.connectionFailed.emit("尚未连接")
            return
        try:
            nss = list_namespaces(self._client)
        except Exception as e:
            self.connectionFailed.emit(str(e))
            return
        self.ns_combo.clear()
        self.ns_combo.addItems(nss)
        self.namespacesLoaded.emit(nss)
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/host_ns_selector.py
git commit -m "feat: 共享组件HostNamespaceSelector（选主机→自动连→命名空间）"
```

---

### Task 10: 页面① 主机管理（src/ui/host_page.py）

**Files:**
- Create: `src/ui/host_page.py`

- [ ] **Step 1: 实现**

```python
# src/ui/host_page.py
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..config import hosts_to_config, load_config, save_config
from ..models import HostConfig
from ..ssh_client import SSHClient


class _TestWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, host: HostConfig, parent=None):
        super().__init__(parent)
        self.host = host

    def run(self):
        try:
            SSHClient(self.host.ip, self.host.port, self.host.username, self.host.password).connect()
            self.done.emit(True, "连接成功")
        except Exception as e:
            self.done.emit(False, f"连接失败: {e}")


class HostPage(QWidget):
    hostsChanged = Signal()   # 主机列表变更，通知其他页刷新下拉

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hosts = self._load()
        self._worker = None
        self._build_ui()
        self.refresh_table()

    def _load(self):
        data = load_config()
        return hosts_from_config(data)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["IP", "端口", "账号", "备注"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table, 1)

        form = QVBoxLayout()
        form.addWidget(QLabel("IP:"))
        self.ip_edit = QLineEdit()
        form.addWidget(self.ip_edit)
        form.addWidget(QLabel("端口:"))
        self.port_edit = QLineEdit("22")
        form.addWidget(self.port_edit)
        form.addWidget(QLabel("账号:"))
        self.user_edit = QLineEdit()
        form.addWidget(self.user_edit)
        form.addWidget(QLabel("密码:"))
        self.pwd_edit = QLineEdit()
        self.pwd_edit.setEchoMode(QLineEdit.Password)
        form.addWidget(self.pwd_edit)
        form.addWidget(QLabel("备注:"))
        self.remark_edit = QLineEdit()
        form.addWidget(self.remark_edit)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("新增")
        self.update_btn = QPushButton("更新")
        self.del_btn = QPushButton("删除")
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.update_btn)
        btn_row.addWidget(self.del_btn)
        form.addLayout(btn_row)
        self.test_btn = QPushButton("测试连接")
        form.addWidget(self.test_btn)
        self.status_label = QLabel("")
        form.addWidget(self.status_label)
        form.addStretch(1)

        wrap = QWidget()
        wrap.setLayout(form)
        layout.addWidget(wrap)

        self.add_btn.clicked.connect(self.add_host)
        self.update_btn.clicked.connect(self.update_host)
        self.del_btn.clicked.connect(self.delete_host)
        self.test_btn.clicked.connect(self.test_connection)
        self.table.itemSelectionChanged.connect(self._load_selected)

    def refresh_table(self):
        self.table.setRowCount(0)
        for i, h in enumerate(self.hosts):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(h.ip))
            self.table.setItem(i, 1, QTableWidgetItem(str(h.port)))
            self.table.setItem(i, 2, QTableWidgetItem(h.username))
            self.table.setItem(i, 3, QTableWidgetItem(h.remark))

    def _load_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.hosts):
            return
        h = self.hosts[row]
        self.ip_edit.setText(h.ip)
        self.port_edit.setText(str(h.port))
        self.user_edit.setText(h.username)
        self.pwd_edit.setText(h.password)
        self.remark_edit.setText(h.remark)

    def _form_host(self):
        return HostConfig(
            ip=self.ip_edit.text().strip(),
            port=int(self.port_edit.text().strip() or 22),
            username=self.user_edit.text().strip(),
            password=self.pwd_edit.text(),
            remark=self.remark_edit.text().strip(),
        )

    def _persist(self):
        data = load_config()
        data["hosts"] = hosts_to_config(self.hosts)
        save_config(data)
        self.refresh_table()
        self.hostsChanged.emit()

    def add_host(self):
        h = self._form_host()
        if not h.ip or not h.username:
            QMessageBox.warning(self, "提示", "IP 和账号必填")
            return
        self.hosts.append(h)
        self._persist()

    def update_host(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择要更新的行")
            return
        self.hosts[row] = self._form_host()
        self._persist()

    def delete_host(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的行")
            return
        del self.hosts[row]
        self._persist()

    def test_connection(self):
        h = self._form_host()
        if not h.ip:
            QMessageBox.warning(self, "提示", "IP 必填")
            return
        self.status_label.setText("测试中...")
        self.test_btn.setEnabled(False)
        self._worker = _TestWorker(h, self)
        self._worker.done.connect(self._on_test_done)
        self._worker.start()

    def _on_test_done(self, ok, msg):
        self.status_label.setText(msg)
        self.test_btn.setEnabled(True)
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/host_page.py
git commit -m "feat: 页面① 主机管理（增删改+测试连接）"
```

---

### Task 11: 页面② 日志抓取（src/ui/collect_page.py）

**Files:**
- Create: `src/ui/collect_page.py`

- [ ] **Step 1: 实现**

```python
# src/ui/collect_page.py
import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QProgressBar, QPushButton, QRadioButton,
                               QVBoxLayout, QWidget)

from ..collector import Collector, write_manifest, zip_output
from ..config import load_config, save_config
from ..k8s_client import PATTERN_MAP, get_pods_meta
from ..models import CollectSummary, CollectTask
from .host_ns_selector import HostNamespaceSelector
from .log_panel import LogPanel


class _CollectWorker(QThread):
    progress = Signal(object)                  # CollectResult
    finished_ok = Signal(object, object, object)  # (results, metas, summary)
    error = Signal(str)

    def __init__(self, tasks, metas, output_base, namespace, ssh_provider, parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self.metas = metas
        self.output_base = output_base
        self.namespace = namespace
        self.ssh_provider = ssh_provider
        self.cancel = Event()

    def cancel_request(self):
        self.cancel.set()

    def run(self):
        try:
            collector = Collector(self.ssh_provider, self.output_base, max_workers=4)
            results = collector.run(self.tasks, on_progress=self.progress.emit, cancel=self.cancel)
            summary = CollectSummary.build(results)
            self.finished_ok.emit(results, self.metas, summary)
        except Exception as e:
            self.error.emit(str(e))


class CollectPage(QWidget):
    def __init__(self, hosts_provider, parent=None):
        super().__init__(parent)
        self._worker = None
        self.metas = []
        self._date_name = datetime.datetime.now().strftime("%Y-%m-%d")

        root = QVBoxLayout(self)
        self.selector = HostNamespaceSelector(hosts_provider, self)
        root.addWidget(self.selector)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("存储目录:"))
        self.out_label = QLabel()
        out_row.addWidget(self.out_label, 1)
        self.choose_btn = QPushButton("选择存储目录")
        out_row.addWidget(self.choose_btn)
        root.addLayout(out_row)

        pod_group = QGroupBox("Pod 选择")
        pod_layout = QVBoxLayout(pod_group)
        mode_row = QHBoxLayout()
        self.all_radio = QRadioButton("全部 Pod")
        self.pick_radio = QRadioButton("手动勾选")
        self.all_radio.setChecked(True)
        mode_row.addWidget(self.all_radio)
        mode_row.addWidget(self.pick_radio)
        mode_row.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索 Pod 名 / 部署名...")
        mode_row.addWidget(self.search_edit)
        pod_layout.addLayout(mode_row)
        self.pod_list = QListWidget()
        self.pod_list.setSelectionMode(QListWidget.NoSelection)
        pod_layout.addWidget(self.pod_list, 1)
        root.addWidget(pod_group, 1)

        cat_row = QHBoxLayout()
        cat_row.addWidget(QLabel("日志类别:"))
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(list(PATTERN_MAP.keys()))
        cat_row.addWidget(self.cat_combo)
        cat_row.addStretch(1)
        self.start_btn = QPushButton("开始采集")
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setEnabled(False)
        cat_row.addWidget(self.start_btn)
        cat_row.addWidget(self.cancel_btn)
        root.addLayout(cat_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log_panel = LogPanel()
        root.addWidget(self.log_panel, 1)

        self.selector.namespacesLoaded.connect(lambda _n: self._load_pods())
        self.selector.connectionFailed.connect(self._on_error)
        self.choose_btn.clicked.connect(self._choose_dir)
        self.start_btn.clicked.connect(self.start_collect)
        self.cancel_btn.clicked.connect(self._cancel)
        self.all_radio.toggled.connect(lambda _: self._update_pod_state())
        self.search_edit.textChanged.connect(self._filter_pods)

        cfg = load_config()
        self.out_dir = Path(cfg.get("output_dir") or str(Path.cwd() / "output"))
        self._update_out_label()

    def _update_out_label(self):
        self.out_label.setText(str(self.out_dir))

    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择存储目录", str(self.out_dir))
        if d:
            self.out_dir = Path(d)
            data = load_config()
            data["output_dir"] = str(self.out_dir)
            save_config(data)
            self._update_out_label()

    def _load_pods(self):
        ns = self.selector.ns_combo.currentText()
        if not ns:
            return
        try:
            self.metas = get_pods_meta(self.selector.client(), ns)
        except Exception as e:
            self._on_error(f"加载 Pod 失败: {e}")
            return
        self.pod_list.clear()
        for pm in self.metas:
            item = QListWidgetItem(f"[{pm.deploy_name}]  {pm.name}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, pm.name)
            self.pod_list.addItem(item)
        self.log_panel.append_log(f"命名空间 {ns} 共加载 {len(self.metas)} 个 Pod")

    def _filter_pods(self, text):
        text = text.strip().lower()
        for i in range(self.pod_list.count()):
            item = self.pod_list.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())

    def _update_pod_state(self):
        pick = self.pick_radio.isChecked()
        for i in range(self.pod_list.count()):
            item = self.pod_list.item(i)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable if pick
                          else item.flags() & ~Qt.ItemIsUserCheckable)

    def _selected_pods(self):
        if self.all_radio.isChecked():
            return [pm.name for pm in self.metas]
        return [self.pod_list.item(i).data(Qt.UserRole)
                for i in range(self.pod_list.count())
                if not self.pod_list.item(i).isHidden()
                and self.pod_list.item(i).checkState() == Qt.Checked]

    def start_collect(self):
        ns = self.selector.ns_combo.currentText()
        if not ns or not self.metas:
            self._on_error("请先选择命名空间并加载 Pod")
            return
        pod_names = self._selected_pods()
        if not pod_names:
            self._on_error("没有选中的 Pod")
            return
        category = self.cat_combo.currentText()
        pattern = PATTERN_MAP[category]
        by_name = {pm.name: pm for pm in self.metas}
        tasks = [CollectTask(pod_name=n, deploy_name=by_name[n].deploy_name,
                             namespace=ns, pattern=pattern) for n in pod_names]
        date_dir = self.out_dir / self._date_name
        date_dir.mkdir(parents=True, exist_ok=True)
        self.progress.setRange(0, len(tasks))
        self.progress.setValue(0)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_panel.clear_log()
        self.log_panel.append_log(
            f"开始采集：{len(tasks)} 个 Pod，类别={category}，存储={self.out_dir}")
        self._worker = _CollectWorker(
            tasks, self.metas, self.out_dir, ns,
            lambda: self.selector.client(), self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_progress(self, result):
        if result.ok:
            self.log_panel.append_log(f"  ✓ {result.pod_name}：{result.file_count} 个文件")
        else:
            self.log_panel.append_log(f"  - {result.pod_name}：{result.error}")
        self.progress.setValue(self.progress.value() + 1)

    def _on_finished(self, results, metas, summary):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        ns = self.selector.ns_combo.currentText()
        category = self.cat_combo.currentText()
        manifest_path = self.out_dir / self._date_name / "pods_manifest.json"
        write_manifest(manifest_path, ns, metas, results)
        zip_path = zip_output(self.out_dir, self._date_name, ns, category)
        self.log_panel.append_log(
            f"完成：成功 {summary.ok} / 跳过 {summary.skipped} / 失败 {summary.failed}")
        self.log_panel.append_log(f"压缩包：{zip_path}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.out_dir)))

    def _cancel(self):
        if self._worker:
            self._worker.cancel_request()
            self.log_panel.append_log("取消请求已发送，正在停止...")

    def _on_error(self, msg):
        self.log_panel.append_log(f"[错误] {msg}")

    def _on_worker_error(self, msg):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.log_panel.append_log(f"[错误] {msg}")
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/collect_page.py
git commit -m "feat: 页面② 日志抓取（选主机/命名空间/Pod/类别/进度）"
```

---

### Task 12: 页面③ 查询分析（src/ui/analyze_page.py）

**Files:**
- Create: `src/ui/analyze_page.py`
- Test: `tests/test_analyze_filter.py`

- [ ] **Step 1: 写失败测试（字段取值纯逻辑）**

```python
# tests/test_analyze_filter.py
from src.models import PodMeta
from src.ui.analyze_page import _field_value

def test_field_value_priority():
    pm = PodMeta(
        name="pod1", namespace="ns1", deploy_name="app",
        labels={"project": "p1"}, annotations={"uuid": "u1", "deployName": "app"},
        full_json={"spec": {"containers": [{"image": "img:v1"}]}},
    )
    assert _field_value(pm, "deployName") == "app"
    assert _field_value(pm, "project") == "p1"
    assert _field_value(pm, "uuid") == "u1"
    assert _field_value(pm, "image") == "img:v1"
    assert _field_value(pm, "node") == ""
```

- [ ] **Step 2: 运行确认失败**

运行：`python -m pytest tests/test_analyze_filter.py -v`
预期：`ModuleNotFoundError: No module named 'src.ui.analyze_page'`

- [ ] **Step 3: 实现**

```python
# src/ui/analyze_page.py
import json
from collections import Counter

from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QDialogButtonBox, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..k8s_client import get_pods_meta
from ..models import PodMeta
from .host_ns_selector import HostNamespaceSelector

FILTER_FIELDS = ["deployName", "project", "namespace", "node", "image",
                 "pipelineName", "uuid", "podIP", "src", "status", "pod"]


def _field_value(pm: PodMeta, field: str) -> str:
    """从 PodMeta 各来源取字段值：显式映射 → labels → annotations → 特殊字段。"""
    mapping = {
        "deployName": pm.deploy_name,
        "pod": pm.name,
        "namespace": pm.namespace,
        "node": pm.node,
        "podIP": pm.pod_ip,
        "status": pm.status,
    }
    if field in mapping:
        return mapping[field]
    if field in pm.labels:
        return pm.labels[field]
    if field in pm.annotations:
        return pm.annotations[field]
    if field == "uuid":
        return pm.annotations.get("uuid", "")
    if field == "image":
        containers = pm.full_json.get("spec", {}).get("containers", [])
        return containers[0].get("image", "") if containers else ""
    return ""


class AnalyzePage(QWidget):
    def __init__(self, hosts_provider, parent=None):
        super().__init__(parent)
        self.metas = []

        root = QVBoxLayout(self)
        self.selector = HostNamespaceSelector(hosts_provider, self)
        root.addWidget(self.selector)

        # 条件过滤：固定 3 个条件行（字段/操作/值），够用且简单
        cond_group = QGroupBox("条件过滤（多条件 AND）")
        cond_layout = QVBoxLayout(cond_group)
        self.cond_rows = []
        for _ in range(3):
            row = QHBoxLayout()
            field = QComboBox()
            field.addItems(FILTER_FIELDS)
            op = QComboBox()
            op.addItems(["等于", "包含"])
            value = QLineEdit()
            row.addWidget(field)
            row.addWidget(op)
            row.addWidget(value, 1)
            cond_layout.addLayout(row)
            self.cond_rows.append((field, op, value))
        btn_row = QHBoxLayout()
        self.query_btn = QPushButton("查询")
        self.clear_btn = QPushButton("清空条件")
        btn_row.addWidget(self.query_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch(1)
        cond_layout.addLayout(btn_row)
        root.addWidget(cond_group)

        # 分组统计
        grp_row = QHBoxLayout()
        grp_row.addWidget(QLabel("分组字段:"))
        self.group_combo = QComboBox()
        self.group_combo.addItems(["node", "project", "deployName", "image", "status"])
        grp_row.addWidget(self.group_combo)
        self.group_btn = QPushButton("统计")
        grp_row.addWidget(self.group_btn)
        grp_row.addWidget(QLabel("结果:"))
        self.group_result = QLabel("")
        grp_row.addWidget(self.group_result, 1)
        root.addLayout(grp_row)

        # 关键字搜索
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("关键字搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("匹配 deployName/image/node/project/pod...")
        search_row.addWidget(self.search_edit, 1)
        self.search_btn = QPushButton("搜索")
        search_row.addWidget(self.search_btn)
        root.addLayout(search_row)

        # 结果表格
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["deployName", "pod", "project", "node", "image", "podIP", "restartCount", "startTime"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemDoubleClicked.connect(self._show_detail)
        root.addWidget(self.table, 1)

        self.selector.namespacesLoaded.connect(lambda _n: self._load_pods())
        self.selector.connectionFailed.connect(lambda _m: self.table.setRowCount(0))
        self.query_btn.clicked.connect(self._apply_query)
        self.clear_btn.clicked.connect(self._clear_conditions)
        self.group_btn.clicked.connect(self._group_stats)
        self.search_btn.clicked.connect(self._apply_query)

    def _load_pods(self):
        ns = self.selector.ns_combo.currentText()
        if not ns:
            return
        try:
            self.metas = get_pods_meta(self.selector.client(), ns)
        except Exception as e:
            self.table.setRowCount(0)
            self.group_result.setText(f"加载 Pod 失败: {e}")
            return
        self._apply_query()

    def _clear_conditions(self):
        for _, _, value in self.cond_rows:
            value.clear()
        self.search_edit.clear()

    def _apply_query(self):
        if not self.metas:
            return
        metas = list(self.metas)
        for field, op, value in self.cond_rows:
            text = value.text().strip()
            if not text:
                continue
            metas = [pm for pm in metas
                     if self._match(pm, field.currentText(), op.currentText(), text)]
        kw = self.search_edit.text().strip().lower()
        if kw:
            metas = [pm for pm in metas
                     if any(kw in _field_value(pm, f).lower()
                            for f in ["deployName", "image", "node", "project", "pod"])]
        self._fill_table(metas)

    def _match(self, pm, field, op, text):
        val = _field_value(pm, field)
        return val == text if op == "等于" else text.lower() in val.lower()

    def _fill_table(self, metas):
        self.table.setRowCount(0)
        for i, pm in enumerate(metas):
            s = pm.summary()
            values = [s["deployName"], pm.name, s["project"], s["node"], s["image"],
                      s["podIP"], str(s["restartCount"]), s["startTime"]]
            self.table.insertRow(i)
            for j, v in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(v))
            self.table.item(i, 0).setData(Qt.UserRole, pm)

    def _group_stats(self):
        if not self.metas:
            return
        field = self.group_combo.currentText()
        counter = Counter(_field_value(pm, field) or "(空)" for pm in self.metas)
        top = counter.most_common(8)
        self.group_result.setText("  ".join(f"{k}: {n}" for k, n in top))

    def _show_detail(self, item):
        pm = item.data(Qt.UserRole)
        if not pm:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(pm.name)
        lay = QVBoxLayout(dlg)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(json.dumps(pm.full_json, ensure_ascii=False, indent=2))
        lay.addWidget(text)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(dlg.reject)
        lay.addWidget(box)
        dlg.resize(720, 560)
        dlg.exec()
```

> 需在文件顶部补 import：`from PySide6.QtCore import Qt`。

- [ ] **Step 4: 运行确认通过**

运行：`python -m pytest tests/test_analyze_filter.py -v`
预期：1 passed

- [ ] **Step 5: Commit**

```bash
git add src/ui/analyze_page.py tests/test_analyze_filter.py
git commit -m "feat: 页面③ 查询分析（过滤/分组/搜索/明细）+ 字段取值单测"
```

---

### Task 13: 主窗口 + 入口（src/ui/main_window.py、main.py）

**Files:**
- Create: `src/ui/main_window.py`
- Create: `main.py`
- Test: `tests/test_ui_smoke.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ui_smoke.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_main_window_constructs(app):
    from src.ui.main_window import MainWindow
    win = MainWindow()
    assert win.stack.count() == 3
    assert win.nav.count() == 3
    win.close()


def test_host_page_add_and_delete(app):
    from src.ui.host_page import HostPage
    page = HostPage()
    page.ip_edit.setText("10.0.0.1")
    page.user_edit.setText("root")
    page.pwd_edit.setText("pw")
    page.add_host()
    assert page.table.rowCount() == 1
    page.delete_host()
    assert page.table.rowCount() == 0
```

> 注：`test_host_page_add_and_delete` 会真实写入 `~/.k8s_log_getter/config.json`。若需隔离，可在测试里 monkeypatch `src.ui.host_page.CONFIG_PATH` 到 tmp_path。执行者选择其一即可，不影响断言逻辑。

- [ ] **Step 2: 运行确认失败**

运行：`python -m pytest tests/test_ui_smoke.py -v`
预期：`ModuleNotFoundError: No module named 'src.ui.main_window'`

- [ ] **Step 3: 实现主窗口**

```python
# src/ui/main_window.py
from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QListWidgetItem,
                               QMainWindow, QStackedWidget, QWidget)

from ..config import hosts_from_config, load_config
from .analyze_page import AnalyzePage
from .collect_page import CollectPage
from .host_page import HostPage


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("K8S 日志采集与分析工具")
        self.resize(1100, 720)

        central = QWidget()
        layout = QHBoxLayout(central)
        self.nav = QListWidget()
        self.nav.setFixedWidth(150)
        for name in ("① 主机配置", "② 日志抓取", "③ 查询分析"):
            self.nav.addItem(QListWidgetItem(name))
        layout.addWidget(self.nav)

        self.stack = QStackedWidget()
        self.host_page = HostPage(self)
        self.collect_page = CollectPage(self._hosts_provider, self)
        self.analyze_page = AnalyzePage(self._hosts_provider, self)
        self.stack.addWidget(self.host_page)
        self.stack.addWidget(self.collect_page)
        self.stack.addWidget(self.analyze_page)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        self.host_page.hostsChanged.connect(self._refresh_selector_hosts)
        self._refresh_selector_hosts()

    def _hosts_provider(self):
        return hosts_from_config(load_config())

    def _refresh_selector_hosts(self):
        self.collect_page.selector.refresh_hosts()
        self.analyze_page.selector.refresh_hosts()
```

- [ ] **Step 4: 实现入口**

```python
# main.py
import sys

from PySide6.QtWidgets import QApplication

from src.config import APP_DIR
from src.logger import setup_logging
from src.ui.main_window import MainWindow


def main():
    setup_logging(APP_DIR / "logs")
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 运行确认通过**

运行：`python -m pytest tests/test_ui_smoke.py -v`
预期：2 passed

- [ ] **Step 6: 手动启动验证**

运行：`python main.py`
预期：窗口打开，左侧三个页签；切到「① 主机配置」可新增主机（填假 IP 点测试连接会失败提示，属正常）。

- [ ] **Step 7: Commit**

```bash
git add src/ui/main_window.py main.py tests/test_ui_smoke.py
git commit -m "feat: 主窗口三页签 + 入口main.py + UI冒烟测试"
```

---

### Task 14: 端到端冒烟 + README

**Files:**
- Modify: `README.md`
- Create: `tests/test_e2e_local.py`

- [ ] **Step 1: 写本地端到端测试（不连真实集群，用本地 tar 模拟远端）**

```python
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

    results = Collector(factory, out_base, max_workers=2).run(tasks, cancel=Event())
    summary = CollectSummary.build(results)
    assert summary.ok == 2

    write_manifest(out_base / date_name / "pods_manifest.json", ns, metas, results)
    manifest = json.loads((out_base / date_name / "pods_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["pods"]) == 2

    z = zip_output(out_base, date_name, ns, "ALL")
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        assert any("ppl2-a/hycommon.log" in n for n in names)
        assert any("pods_manifest.json" in n for n in names)

    assert (out_base / ns / "ppl2" / "ppl2-a" / "hycommon.log").exists()
```

- [ ] **Step 2: 运行端到端测试**

运行：`python -m pytest tests/test_e2e_local.py -v`
预期：1 passed

- [ ] **Step 3: 更新 README**

```markdown
# K8S 日志采集与分析工具

PySide6 + paramiko 实现的 K8S 日志工具（Windows / macOS）。

## 三页面

1. **① 主机配置**：SSH 主机增删改、测试连接；密码 base64 存储
2. **② 日志抓取**：选主机→自动连→命名空间→Pod（全部/勾选）× 日志类别（ALL/hycommon/hyframework）→ 并发采集 → zip + manifest
3. **③ 查询分析**：Pod 元数据条件过滤 / 分组统计 / 关键字搜索 / 明细查看

## 运行

```bash
python -m pip install -r requirements.txt
python main.py
```

## 测试

```bash
python -m pytest -v
```

## 说明

- 日志默认存 `./output/<日期>/<命名空间>/<部署名>/<Pod>/`，可在页面②选择存储目录
- 采集用 `tar czf -` 流式下载 + 4 线程并发，输出含 `pods_manifest.json`（完整 Pod JSON + 摘要）
- 配置存 `~/.k8s_log_getter/config.json`，软件自身日志存 `~/.k8s_log_getter/logs/app.log`
```

- [ ] **Step 4: 运行全部测试**

运行：`python -m pytest -v`
预期：全部通过（models/config/logger/ssh/k8s/collector/analyze/ui/e2e）

- [ ] **Step 5: Commit**

```bash
git add tests/test_e2e_local.py README.md
git commit -m "docs: README；test: 本地端到端冒烟"
```

---

## 自审记录

- **Spec 覆盖**：三页面（Task 10/11/12）、HostNamespaceSelector（Task 9）、tar+并发（Task 7）、部署名分组+manifest（Task 7）、base64 密码（Task 4）、软件日志（Task 2）、输出目录可自定义（Task 11）、跨平台（pathlib 全路径、offscreen UI 测试）。
- **占位符**：无 TBD。Task 12 采用「固定 3 个条件行」的简单方案替代动态添加，能力等价（过滤/分组/搜索/明细完整）。
- **类型一致**：`CollectTask(pod_name, deploy_name, namespace, pattern)`、`CollectResult(pod_name, ok, file_count, error)`、`PodMeta.summary()`、`PATTERN_MAP` 在各 Task 中签名一致；`_CollectWorker` 的 `ssh_provider` 参数在 Task 11 定义与使用一致。
