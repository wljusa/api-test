# -*- coding: utf-8 -*-
"""会话态读写。登录得到的 token 按环境落在 extract_<env>.yaml。"""
import os
from typing import Any, Optional

import yaml

import config


def _path(file_path: Optional[str]) -> str:
    return file_path or config.extract_path()


def load_store(file_path: Optional[str] = None) -> dict:
    path = _path(file_path)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return {}
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("会话文件根节点必须是映射: %s" % path)
    return data


def write_values(data: dict, file_path: Optional[str] = None) -> None:
    path = _path(file_path)
    current = load_store(path)
    current.update(data)
    with open(path, encoding="utf-8", mode="w") as handle:
        yaml.safe_dump(current, handle, allow_unicode=True, sort_keys=False)


def read_value(key: str, file_path: Optional[str] = None) -> Any:
    return load_store(file_path).get(key)


def clear_store(file_path: Optional[str] = None) -> None:
    path = _path(file_path)
    with open(path, encoding="utf-8", mode="w") as handle:
        handle.write("")
