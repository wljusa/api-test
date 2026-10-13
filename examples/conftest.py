# -*- coding: utf-8 -*-
import socket
import threading
import time

import pytest

import config
from examples.mock_app import create_server, parse_base_url
from framework.case_loader import read_env_testcase
from framework.client import ApiClient
from framework.store import clear_store


@pytest.fixture(scope="session", autouse=True)
def _clear_extract():
    clear_store()
    yield


@pytest.fixture(scope="session", autouse=True)
def mock_server():
    base_url = config.CLIENTS["app"]["base_url"]
    httpd = create_server(base_url)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = parse_base_url(base_url)
    deadline = time.time() + 3
    last_error = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                last_error = None
                break
        except OSError as exc:
            last_error = exc
            time.sleep(0.05)
    if last_error is not None:
        httpd.shutdown()
        httpd.server_close()
        raise RuntimeError("示例服务未就绪: %s" % last_error)
    yield httpd
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture(scope="session")
def app_login(mock_server):
    success = None
    for case in read_env_testcase("login.yaml"):
        if case["request"]["validate"].get("code") == 0:
            success = case
            break
    if success is None:
        pytest.fail("login.yaml 缺少 code 为 0 的登录场景")
    ApiClient("app").login(success)
