import io
import json
import tarfile

import pytest

from pathlib import Path

from src.k8s_client import (PATTERN_MAP, TAR_PROBE_MARK, build_cat_command,
                            build_log_pattern, build_tar_command,
                            collect_pod_logs, count_tar_files, get_pods_meta,
                            has_tar_command, list_namespaces, pack_stream_to_tar,
                            parse_pods_json)


class _FakeClient:
    def __init__(self, result):
        self._result = result

    def exec_stdout(self, cmd, timeout=60):
        return self._result


class _FakeStreamClient(_FakeClient):
    """记录 stream_to_file 命令，把 payload 写入目标文件后返回指定退出码。

    result 同时充当 exec_stdout 的返回（tar 探测）：回显 TAR_PROBE_MARK 即视为有 tar。
    """

    def __init__(self, result, stream_result=0, payload=b""):
        super().__init__(result)
        self._stream_result = stream_result
        self._payload = payload
        self.stream_cmd = ""

    def stream_to_file(self, cmd, filepath, timeout=600):
        self.stream_cmd = cmd
        Path(filepath).write_bytes(self._payload)
        return self._stream_result


def _has_tar_probe():
    """tar 探测命中：容器内有 tar。"""
    return (0, f"{TAR_PROBE_MARK}\n", "")


def _no_tar_probe():
    """tar 探测未命中：容器内没有 tar 命令。"""
    return (1, "", "sh: tar: not found")


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


def test_build_tar_command_sanitizes_pattern():
    """通配符模式同样不允许携带 shell 元字符。"""
    cmd = build_tar_command("ns1", "pod1", "$(whoami).log")
    assert "$(" not in cmd
    assert "whoami.log" in cmd


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


def test_collect_pod_logs_uses_tar_when_available(tmp_path):
    c = _FakeStreamClient(
        _has_tar_probe(), stream_result=0, payload=_make_tar_bytes(["a.log", "b.log"]))
    target = tmp_path / "logs.tgz"
    n = collect_pod_logs(c, "ns1", "pod1", "*.log", target)
    assert n == 2
    assert target.exists()
    assert "kubectl exec -n ns1 pod1" in c.stream_cmd
    assert "tar czf -" in c.stream_cmd


def test_collect_pod_logs_uses_log_dir(tmp_path):
    c = _FakeStreamClient(_has_tar_probe(), stream_result=0,
                          payload=_make_tar_bytes(["a.log"]))
    target = tmp_path / "logs.tgz"
    collect_pod_logs(c, "ns1", "pod1", "*.log", target, log_dir="/data/logs")
    assert target.exists()
    assert "cd /data/logs" in c.stream_cmd


def test_collect_pod_logs_tar_failure_removes_partial_and_raises(tmp_path):
    c = _FakeStreamClient(_has_tar_probe(), stream_result=1, payload=b"partial tar")
    target = tmp_path / "logs.tgz"
    with pytest.raises(RuntimeError, match="tar 拉取失败"):
        collect_pod_logs(c, "ns1", "pod1", "*.log", target)
    assert not target.exists()


def test_has_tar_command_true_when_container_has_tar():
    c = _FakeClient(_has_tar_probe())
    assert has_tar_command(c, "ns1", "pod1") is True


def test_has_tar_command_false_when_container_lacks_tar():
    c = _FakeClient(_no_tar_probe())
    assert has_tar_command(c, "ns1", "pod1") is False


def test_has_tar_command_false_when_probe_exit_nonzero():
    """探测命令本身失败（如容器没有 sh）也按「没有 tar」处理，交给降级路径尝试。"""
    c = _FakeClient((126, "", "exec: \"sh\": executable file not found"))
    assert has_tar_command(c, "ns1", "pod1") is False


def test_build_cat_command_contains_dir_and_pattern():
    cmd = build_cat_command("ns1", "pod1", "hycommon*.log")
    assert "kubectl exec -n ns1 pod1" in cmd
    assert "cd /opt/logs" in cmd
    assert "hycommon*.log" in cmd
    assert "wc -c" in cmd
    assert "cat " in cmd


def test_build_cat_command_custom_log_dir():
    cmd = build_cat_command("ns1", "pod1", "*.log", log_dir="/data/logs")
    assert "cd /data/logs" in cmd


def test_build_cat_command_sanitizes_log_dir():
    """日志目录不允许携带 shell 元字符（命令本身含 `;`，断言只看拼进去的目录）。"""
    cmd = build_cat_command("ns1", "pod1", "*.log", log_dir="/logs; rm -rf /")
    assert "/logs; rm -rf /" not in cmd
    assert "cd /logsrm-rf/" in cmd


def test_pack_stream_to_tar_roundtrip(tmp_path):
    """正文按字节数精确切分：内容里出现 "L:" 也不会被当成下一个文件头。"""
    raw = b"L:a.log\n7\nabcL:9\nL:b.log\n5\nhello"
    raw_path = tmp_path / "s.raw"
    raw_path.write_bytes(raw)
    tar_path = tmp_path / "out.tar.gz"
    assert pack_stream_to_tar(raw_path, tar_path) == 2
    with tarfile.open(tar_path, "r:gz") as tf:
        assert tf.getnames() == ["a.log", "b.log"]
        assert tf.extractfile("a.log").read() == b"abcL:9\n"
        assert tf.extractfile("b.log").read() == b"hello"


def test_pack_stream_to_tar_sets_sane_mtime(tmp_path):
    """TarInfo 默认 mtime=0 → 解压出的文件是 1970，ZIP 不支持 <1980 会直接崩。"""
    raw_path = tmp_path / "s.raw"
    raw_path.write_bytes(b"L:a.log\n3\nabc")
    tar_path = tmp_path / "out.tar.gz"
    pack_stream_to_tar(raw_path, tar_path)
    with tarfile.open(tar_path, "r:gz") as tf:
        assert tf.getmember("a.log").mtime >= 315532800  # 1980-01-01 UTC


def test_pack_stream_to_tar_empty_stream_is_zero(tmp_path):
    """容器里没有匹配文件时降级流为空，产出空包、文件数 0（下游记为「无匹配日志」）。"""
    raw_path = tmp_path / "s.raw"
    raw_path.write_bytes(b"")
    tar_path = tmp_path / "out.tar.gz"
    assert pack_stream_to_tar(raw_path, tar_path) == 0
    assert count_tar_files(tar_path) == 0


def test_pack_stream_to_tar_truncated_raises_and_cleans(tmp_path):
    """正文短于头部声明的长度（cat 中途断流）必须报错，不能产出半截包。"""
    raw_path = tmp_path / "s.raw"
    raw_path.write_bytes(b"L:a.log\n99\nshort")
    tar_path = tmp_path / "out.tar.gz"
    with pytest.raises(RuntimeError, match="截断"):
        pack_stream_to_tar(raw_path, tar_path)
    assert not tar_path.exists()


def test_pack_stream_to_tar_bad_header_raises_and_cleans(tmp_path):
    raw_path = tmp_path / "s.raw"
    raw_path.write_bytes(b"garbage\n")
    tar_path = tmp_path / "out.tar.gz"
    with pytest.raises(RuntimeError, match="格式异常"):
        pack_stream_to_tar(raw_path, tar_path)
    assert not tar_path.exists()


def test_collect_pod_logs_falls_back_when_no_tar(tmp_path):
    c = _FakeStreamClient(_no_tar_probe(), stream_result=0,
                          payload=b"L:a.log\n3\nabcL:b.log\n2\nhi")
    target = tmp_path / "logs.tgz"
    n = collect_pod_logs(c, "ns1", "pod1", "*.log", target)
    assert n == 2
    assert "cat " in c.stream_cmd          # 走的是逐文件 cat，不是 tar
    with tarfile.open(target, "r:gz") as tf:
        assert tf.extractfile("a.log").read() == b"abc"
    # 中间降级流文件必须清理，否则会残留在 Pod 目录里
    assert not (tmp_path / "logs.tgz.raw").exists()


def test_collect_pod_logs_fallback_failure_removes_files(tmp_path):
    """降级命令自身失败（如容器连 sh 都没有）时报错，且不留残留文件。"""
    c = _FakeStreamClient(_no_tar_probe(), stream_result=126, payload=b"")
    target = tmp_path / "logs.tgz"
    with pytest.raises(RuntimeError, match="日志拉取失败"):
        collect_pod_logs(c, "ns1", "pod1", "*.log", target)
    assert not target.exists()
    assert not (tmp_path / "logs.tgz.raw").exists()
