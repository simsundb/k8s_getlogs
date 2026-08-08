from src.models import PodMeta
from src.ui.analyze_page import _describe_meta, _field_value, _searchable_text


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


def test_searchable_text_covers_all_fields():
    pm = PodMeta(
        name="pod1", namespace="ns1", deploy_name="app",
        node="node-x", pod_ip="10.0.0.1", status="Running",
        labels={"project": "p1", "tier": "backend"},
        annotations={"uuid": "u1", "pipelineName": "pipe-z"},
        full_json={"spec": {"containers": [{"image": "img:v1"}]}},
    )
    text = _searchable_text(pm)
    for needle in ["pod1", "app", "node-x", "10.0.0.1", "running",
                   "p1", "backend", "u1", "pipe-z", "img:v1"]:
        assert needle in text
    assert text == text.lower()  # 关键字全字段匹配为大小写不敏感


def test_searchable_text_case_insensitive():
    pm = PodMeta(name="POD-X", namespace="ns", deploy_name="App-Svc",
                 annotations={"uuid": "U-9"})
    assert "pod-x" in _searchable_text(pm)
    assert "app-svc" in _searchable_text(pm)


def test_describe_meta_contains_chinese_labels_and_values():
    pm = PodMeta(
        name="pod1", namespace="ns1", deploy_name="app", node="node-x",
        pod_ip="10.0.0.1", start_time="2026-08-08T10:00:00Z",
        restart_count=2, status="Running",
        labels={"project": "p1"}, annotations={"uuid": "u1"},
        full_json={"spec": {"containers": [{"image": "img:v1",
                                            "env": [{"name": "JAVA_OPTS"}]}]},
                   "status": {"phase": "Running"}},
    )
    desc = _describe_meta(pm)
    for label, value in [("名称", "pod1"), ("命名空间", "ns1"), ("所属部署名", "app"),
                         ("所在节点", "node-x"), ("Pod IP", "10.0.0.1"),
                         ("启动时间", "2026-08-08T10:00:00Z"), ("重启次数", "2"),
                         ("运行状态", "Running"), ("镜像", "img:v1"),
                         ("环境变量", "JAVA_OPTS"), ("标签", "1 项键值对")]:
        assert label in desc, f"缺字段: {label}"
        assert value in desc, f"缺值: {value}"
