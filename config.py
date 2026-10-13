# -*- coding: utf-8 -*-
"""运行环境与客户端配置。

TEST_ENV 在进程启动时读取，默认 test。切换环境需要新的 Python 进程。
"""
import os
from typing import Optional

import yaml

ENV = os.getenv("TEST_ENV", "test")
BASE_PATH = os.path.dirname(os.path.abspath(__file__))


def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("YAML 根节点必须是映射: %s" % path)
    return data


def merge_env_section(
    common: Optional[dict],
    env: Optional[dict],
) -> dict:
    """合并 common 与当前环境节。同名 list 追加，其它类型由环境节覆盖。"""
    merged: dict = dict(common or {})
    for key, value in (env or {}).items():
        if isinstance(merged.get(key), list) and isinstance(value, list):
            merged[key] = list(merged[key]) + list(value)
        else:
            merged[key] = value
    return merged


def _client_base_url(spec: dict, env: str) -> str:
    base_url = spec.get("base_url")
    if isinstance(base_url, dict):
        if env not in base_url:
            raise KeyError("客户端 base_url 缺少环境 %s" % env)
        return str(base_url[env])
    if not base_url:
        raise KeyError("客户端缺少 base_url")
    return str(base_url)


def load_clients(env: str) -> dict:
    raw = load_yaml(os.path.join(BASE_PATH, "config", "clients.yaml"))
    clients = {}
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            raise ValueError("客户端 %s 必须是映射" % name)
        item = dict(spec)
        item["base_url"] = _client_base_url(spec, env)
        item["headers"] = dict(spec.get("headers") or {})
        clients[name] = item
    return clients


_ids_all = load_yaml(os.path.join(BASE_PATH, "config", "env_ids.yaml"))
ENV_IDS: dict = merge_env_section(_ids_all.get("common"), _ids_all.get(ENV))
CLIENTS: dict = load_clients(ENV)


def extract_path() -> str:
    return os.path.join(BASE_PATH, "extract_%s.yaml" % ENV)


def data_root() -> str:
    return os.path.join(BASE_PATH, "examples", "data")
