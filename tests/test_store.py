# -*- coding: utf-8 -*-
from framework.store import clear_store, read_value, write_values


def test_write_read_and_clear():
    assert read_value("app_token") is None
    write_values({"app_token": "demo-token"})
    write_values({"user_id": 1})
    assert read_value("app_token") == "demo-token"
    assert read_value("user_id") == 1
    clear_store()
    assert read_value("app_token") is None
    assert read_value("user_id") is None
