from src.models import NO_MATCH_ERROR, CollectResult, CollectSummary, PodMeta


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
