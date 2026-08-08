from src.models import (NO_MATCH_ERROR, CollectResult, CollectSummary, PodMeta,
                        human_size)


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
    assert r.total_bytes == 0
    assert r.error == ""


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(128) == "128 B"
    assert human_size(1536) == "1.5 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"
    assert human_size(3 * 1024 * 1024 * 1024) == "3.0 GB"


def test_collect_summary_total_bytes():
    s = CollectSummary.build([
        CollectResult(pod_name="p1", ok=True, total_bytes=1000),
        CollectResult(pod_name="p2", ok=True, total_bytes=500),
        CollectResult(pod_name="p3", ok=False, error="boom"),
    ])
    assert s.ok == 2
    assert s.failed == 1
    assert s.total_bytes == 1500  # 只统计成功采集的日志字节


def test_podmeta_summary_missing_spec_containers_gives_empty_image():
    pm = PodMeta(
        name="pod-a",
        namespace="ns",
        deploy_name="deploy-a",
        full_json={},
    )
    s = pm.summary()
    assert s["image"] == ""


def test_podmeta_summary_empty_labels_gives_empty_project():
    pm = PodMeta(
        name="pod-b",
        namespace="ns",
        deploy_name="deploy-b",
        full_json={"spec": {"containers": [{"image": "img"}]}},
    )
    s = pm.summary()
    assert s["project"] == ""


def test_collect_summary_counts_ok():
    s = CollectSummary.build([CollectResult(pod_name="p1", ok=True)])
    assert s.ok == 1
    assert s.skipped == 0
    assert s.failed == 0


def test_collect_summary_counts_skipped():
    s = CollectSummary.build(
        [CollectResult(pod_name="p1", ok=False, error=NO_MATCH_ERROR)]
    )
    assert s.skipped == 1
    assert s.ok == 0
    assert s.failed == 0


def test_collect_summary_counts_failed():
    s = CollectSummary.build(
        [CollectResult(pod_name="p1", ok=False, error="some error")]
    )
    assert s.failed == 1
    assert s.ok == 0
    assert s.skipped == 0


def test_collect_summary_total_invariant_for_mixed_batch():
    results = [
        CollectResult(pod_name="p1", ok=True),
        CollectResult(pod_name="p2", ok=False, error=NO_MATCH_ERROR),
        CollectResult(pod_name="p3", ok=False, error="boom"),
        CollectResult(pod_name="p4", ok=False, error="boom2"),
    ]
    s = CollectSummary.build(results)
    assert s.ok == 1
    assert s.skipped == 1
    assert s.failed == 2
    assert s.total == s.ok + s.skipped + s.failed == 4
