import io
import json
import tarfile

import pytest

from pathlib import Path

from src.k8s_client import (PATTERN_MAP, build_log_pattern, build_tar_command,
                            collect_pod_tar, count_tar_files, get_pods_meta,
                            list_namespaces, parse_pods_json)


class _FakeClient:
    def __init__(self, result):
        self._result = result

    def exec_stdout(self, cmd, timeout=60):
        return self._result


class _FakeStreamClient(_FakeClient):
    """记录 stream_to_file 命令，把 payload 写入目标文件后返回指定退出码。"""

    def __init__(self, result, stream_result=0, payload=b""):
        super().__init__(result)
        self._stream_result = stream_result
        self._payload = payload
        self.stream_cmd = ""

    def stream_to_file(self, cmd, filepath, timeout=600):
        self.stream_cmd = cmd
        Path(filepath).write_bytes(self._payload)
        return self._stream_result


def _make_tar_bytes(names):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name in names:
            info = tarfile.TarInfo(name)
            info.size = 3
            tf.addfile(info, io.BytesIO(b"abc"))
    return buf.getvalue()


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


def test_build_tar_command_custom_log_dir():
    cmd = build_tar_command("ns1", "pod1", "*.log", log_dir="/data/logs")
    assert "cd /data/logs" in cmd


def test_build_tar_command_sanitizes_log_dir():
    """日志目录不允许携带 shell 元字符，防注入远端 sh -c 命令。"""
    cmd = build_tar_command("ns1", "pod1", "*.log", log_dir="/logs; rm -rf /")
    assert ";" not in cmd


def test_build_log_pattern_empty_name_uses_category():
    assert build_log_pattern("ALL", "") == "*.log"
    assert build_log_pattern("hycommon", "") == "hycommon*.log"
    assert build_log_pattern("hyframework", "") == "hyframework*.log"


def test_build_log_pattern_name_matches_containing_log():
    assert build_log_pattern("ALL", "err") == "*err*.log"
    assert build_log_pattern("hycommon", "nginx") == "*nginx*.log"


def test_build_log_pattern_strips_shell_metachars():
    """日志名只保留安全字符，避免被远端 sh 解释成命令/管道。"""
    assert build_log_pattern("ALL", "a;b'c ") == "*abc*.log"


def test_count_tar_files(tmp_path):
    p = tmp_path / "t.tgz"
    with tarfile.open(p, "w:gz") as tf:
        for name in ("a.log", "b.log", "sub/c.log"):
            info = tarfile.TarInfo(name)
            info.size = 3
            tf.addfile(info, io.BytesIO(b"abc"))
    assert count_tar_files(p) == 3


def test_get_pods_meta_ok():
    raw = json.dumps({"items": [
        {
            "metadata": {"name": "p1", "namespace": "ns", "annotations": {"deployName": "d1"}},
            "spec": {},
            "status": {"phase": "Running", "containerStatuses": []},
        },
    ]})
    c = _FakeClient((0, raw, ""))
    metas = get_pods_meta(c, "ns")
    assert len(metas) == 1
    assert metas[0].name == "p1"
    assert metas[0].deploy_name == "d1"


def test_get_pods_meta_failure_raises():
    c = _FakeClient((1, "", "Error from server: not found"))
    with pytest.raises(RuntimeError, match="kubectl get pods"):
        get_pods_meta(c, "ns")


def test_parse_pods_json_absent_container_statuses_defaults_zero():
    raw = json.dumps({"items": [
        {"metadata": {"name": "p1", "namespace": "ns", "annotations": {}},
         "spec": {}, "status": {"phase": "Running"}},
    ]})
    metas = parse_pods_json(raw)
    assert metas[0].restart_count == 0


def test_collect_pod_tar_success_returns_count(tmp_path):
    c = _FakeStreamClient(
        (0, "", ""), stream_result=0, payload=_make_tar_bytes(["a.log", "b.log"]))
    target = tmp_path / "logs.tgz"
    n = collect_pod_tar(c, "ns1", "pod1", "*.log", target)
    assert n == 2
    assert target.exists()
    assert "kubectl exec -n ns1 pod1" in c.stream_cmd


def test_collect_pod_tar_uses_log_dir(tmp_path):
    c = _FakeStreamClient((0, "", ""), stream_result=0,
                          payload=_make_tar_bytes(["a.log"]))
    target = tmp_path / "logs.tgz"
    collect_pod_tar(c, "ns1", "pod1", "*.log", target, log_dir="/data/logs")
    assert target.exists()
    assert "cd /data/logs" in c.stream_cmd


def test_collect_pod_tar_failure_removes_partial_and_raises(tmp_path):
    c = _FakeStreamClient((0, "", ""), stream_result=1, payload=b"partial tar")
    target = tmp_path / "logs.tgz"
    with pytest.raises(RuntimeError, match="tar 拉取失败"):
        collect_pod_tar(c, "ns1", "pod1", "*.log", target)
    assert not target.exists()
