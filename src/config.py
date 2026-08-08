"""K8S 日志采集工具配置读写（JSON + base64 密码混淆）。"""
import base64
import json
import os
from pathlib import Path

from .models import HostConfig

APP_DIR = Path.home() / ".k8s_log_getter"
CONFIG_PATH = APP_DIR / "config.json"


def encode_password(password: str) -> str:
    return base64.b64encode(password.encode("utf-8")).decode("ascii")


def decode_password(encoded: str) -> str:
    if not isinstance(encoded, str):
        raise ValueError("password_b64 必须是字符串")
    return base64.b64decode(encoded, validate=True).decode("utf-8")


def default_config() -> dict:
    return {"hosts": [], "output_dir": ""}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass
    return default_config()


def save_config(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)


def hosts_from_config(data: dict) -> list[HostConfig]:
    items = data.get("hosts", []) if isinstance(data, dict) else data
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            out.append(HostConfig(
                ip=item["ip"],
                port=int(item.get("port", 22)),
                username=item["username"],
                password=decode_password(item["password_b64"]),
                remark=item.get("remark", ""),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def hosts_to_config(hosts: list[HostConfig]) -> list[dict]:
    return [{
        "ip": h.ip,
        "port": h.port,
        "username": h.username,
        "password_b64": encode_password(h.password),
        "remark": h.remark,
    } for h in hosts]
