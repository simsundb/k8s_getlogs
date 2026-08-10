import json

from src.config import (decode_password, default_config, encode_password,
                        hosts_from_config, hosts_to_config, load_config,
                        save_config)
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


def test_hosts_from_config_skips_broken_password_b64():
    data = {"hosts": [
        {"ip": "1.1.1.1", "username": "u", "password_b64": "###"},
        {"ip": "2.2.2.2", "username": "u", "password_b64": 123},
    ]}
    assert hosts_from_config(data) == []


def test_default_config_has_output_dir():
    assert default_config() == {
        "hosts": [], "output_dir": "", "aggregate_after_collect": True,
    }


def test_load_config_missing_file_returns_default(tmp_path, monkeypatch):
    import src.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", tmp_path / "missing.json")
    assert load_config() == {
        "hosts": [], "output_dir": "", "aggregate_after_collect": True,
    }


def test_save_and_load_config_roundtrip(tmp_path, monkeypatch):
    import src.config as cfg
    monkeypatch.setattr(cfg, "APP_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_PATH", tmp_path / "config.json")
    hosts = [HostConfig(ip="5.6.7.8", username="u", password="s3cret")]
    save_config({"hosts": hosts_to_config(hosts), "output_dir": "/data"})
    back = hosts_from_config(load_config())
    assert back[0].ip == "5.6.7.8"
    assert back[0].password == "s3cret"
    raw = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert "s3cret" not in raw


def test_hosts_from_config_skips_non_dict_element():
    data = {"hosts": [
        "oops",
        {
            "ip": "1.2.3.4",
            "username": "u",
            "password_b64": encode_password("x"),
        },
    ]}
    out = hosts_from_config(data)
    assert len(out) == 1
    assert out[0].ip == "1.2.3.4"


def test_hosts_from_config_skips_dict_instead_of_list():
    data = {"hosts": {"ip": "1.2.3.4", "username": "u"}}
    assert hosts_from_config(data) == []


def test_load_config_invalid_json_returns_default(tmp_path, monkeypatch):
    import src.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")
    assert load_config() == {
        "hosts": [], "output_dir": "", "aggregate_after_collect": True,
    }


def test_password_base64_roundtrip_unicode():
    password = "密码P@ss123"
    assert decode_password(encode_password(password)) == password


def test_save_and_load_config_keeps_unicode_remark(tmp_path, monkeypatch):
    import src.config as cfg
    monkeypatch.setattr(cfg, "APP_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_PATH", tmp_path / "config.json")
    hosts = [HostConfig(
        ip="5.6.7.8", username="u", password="pw", remark="生产环境节点")]
    save_config({"hosts": hosts_to_config(hosts), "output_dir": ""})
    back = hosts_from_config(load_config())
    assert back[0].remark == "生产环境节点"
