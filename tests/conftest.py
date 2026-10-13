# -*- coding: utf-8 -*-
import pytest

import config
from framework.client import ApiClient


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    target = tmp_path / "extract.yaml"
    monkeypatch.setattr(config, "extract_path", lambda: str(target))
    ApiClient.reset_elapsed_checked()
    yield target
    ApiClient.reset_elapsed_checked()
