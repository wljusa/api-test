# -*- coding: utf-8 -*-
import os

import config
from framework.case_loader import read_env_testcase, resolve_params


def test_full_placeholder_keeps_type():
    data = {"userId": "${user_id}"}
    resolve_params(data)
    assert data["userId"] == config.ENV_IDS["user_id"]
    assert isinstance(data["userId"], int)


def test_caller_overrides_env_ids():
    data = {"userId": "${user_id}"}
    resolve_params(data, user_id=9)
    assert data["userId"] == 9


def test_inline_placeholder():
    data = {"name": "app-${app_name}"}
    resolve_params(data)
    assert data["name"] == "app-demo"


def test_unknown_placeholder_is_kept():
    data = {"name": "${missing_key}"}
    resolve_params(data)
    assert data["name"] == "${missing_key}"


def test_merge_appends_lists_and_overrides_scalars():
    merged = config.merge_env_section(
        {"ids": [1], "name": "common"},
        {"ids": [2], "name": "env"},
    )
    assert merged["ids"] == [1, 2]
    assert merged["name"] == "env"


def test_common_file_overrides_env(tmp_path):
    common = tmp_path / "common"
    env_dir = tmp_path / config.ENV
    common.mkdir()
    env_dir.mkdir()
    (common / "a.yaml").write_text("- title: common\n", encoding="utf-8")
    (env_dir / "a.yaml").write_text("- title: env\n", encoding="utf-8")
    cases = read_env_testcase("a.yaml", data_root=str(tmp_path))
    assert cases[0]["title"] == "common"


def test_env_file_when_common_missing(tmp_path):
    env_dir = tmp_path / config.ENV
    env_dir.mkdir()
    (env_dir / "a.yaml").write_text("- title: env-only\n", encoding="utf-8")
    cases = read_env_testcase("a.yaml", data_root=str(tmp_path))
    assert cases[0]["title"] == "env-only"
    assert not os.path.exists(tmp_path / "common" / "a.yaml")
