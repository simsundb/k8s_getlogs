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
