# -*- coding: utf-8 -*-
"""读取 YAML 用例，并把 ${key} 替换成环境 ID 或调用方传入的值。"""
import os
import re
import time
from typing import Any, Optional

import yaml

import config

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_FULL_PLACEHOLDER = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def read_testcase(path: str) -> list:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("用例文件根节点必须是列表: %s" % path)
    return data


def read_env_testcase(filename: str, data_root: Optional[str] = None) -> list:
    """common 下有同名文件时优先使用，否则读 data/<TEST_ENV>/。"""
    root = data_root or config.data_root()
    common_path = os.path.join(root, "common", filename)
    if os.path.isfile(common_path):
        return read_testcase(common_path)
    return read_testcase(os.path.join(root, config.ENV, filename))


def _lookup(key: str, ids: dict) -> Any:
    if key in ids:
        return ids[key]
    if key in config.ENV_IDS:
        return config.ENV_IDS[key]
    if key == "ts":
        return int(time.time() * 1000)
    return None


def _resolve_str(value: str, ids: dict) -> Any:
    full = _FULL_PLACEHOLDER.match(value)
    if full:
        found = _lookup(full.group(1), ids)
        return value if found is None else found

    def replace(match: re.Match) -> str:
        found = _lookup(match.group(1), ids)
        return match.group(0) if found is None else str(found)

    return _PLACEHOLDER.sub(replace, value)


def resolve_params(params: Any, **ids: Any) -> Any:
    """就地替换 dict / list / str 中的 ${key}。整段占位符保留原类型。"""
    if isinstance(params, dict):
        for key, value in list(params.items()):
            params[key] = resolve_params(value, **ids)
        return params
    if isinstance(params, list):
        for index, value in enumerate(params):
            params[index] = resolve_params(value, **ids)
        return params
    if isinstance(params, str):
        return _resolve_str(params, ids)
    return params
