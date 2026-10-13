# -*- coding: utf-8 -*-
from types import SimpleNamespace

import pytest

import config
from framework.client import ApiClient, ResponseTimeout
from framework.store import write_values


def _response(body, status=200, elapsed=0.05, url="http://127.0.0.1:8765/api/demo"):
    response = SimpleNamespace(
        status_code=status,
        text="",
        url=url,
        elapsed=SimpleNamespace(total_seconds=lambda: elapsed),
        request=SimpleNamespace(url=url, method="GET", headers={}, body=None),
    )

    def _json():
        return body

    response.json = _json
    return response


def _case(url="/api/demo", **validate):
    fields = {"status_code": 200, "code": 0, "msg": ""}
    fields.update(validate)
    return {
        "feature": "单测",
        "story": "断言",
        "title": "断言",
        "request": {
            "method": "GET",
            "url": url,
            "params": {},
            "validate": fields,
        },
    }


def test_string_code_matches_number():
    client = ApiClient("app")
    client.validate(_response({"code": "0", "msg": "", "data": {}}), _case())


def test_code_mismatch():
    client = ApiClient("app")
    with pytest.raises(AssertionError, match="预期 code: 0, 实际 code: 10016"):
        client.validate(_response({"code": 10016, "msg": ""}), _case())


def test_code_not_rejects_excluded_value():
    client = ApiClient("app")
    case = _case(code_not=[0, 10016])
    case["request"]["validate"].pop("code")
    with pytest.raises(AssertionError, match="预期 code 不在"):
        client.validate(_response({"code": 0, "msg": ""}), case)


def test_missing_fields_only_when_code_is_success():
    client = ApiClient("app")
    case = _case(code=40001, expected_fields=["list"])
    client.validate(_response({"code": 40001, "msg": ""}), case)
    with pytest.raises(AssertionError, match="响应中缺少字段: list"):
        client.validate(_response({"code": 0, "msg": "", "data": {}}), _case(expected_fields=["list"]))


def test_forbidden_ignores_empty_and_reports_nested_value():
    client = ApiClient("app")
    ok = {"code": 0, "msg": "", "data": {"createBy": None, "modifyBy": ""}}
    client.validate(_response(ok), _case(forbidden_fields=["createBy", "modifyBy"]))
    leaked = {"code": 0, "msg": "", "data": {"meta": {"createBy": "alice"}}}
    with pytest.raises(AssertionError, match=r"data\.meta\.createBy"):
        client.validate(
            _response(leaked),
            _case(forbidden_fields=["createBy"]),
        )


def test_status_accepts_any_listed_code():
    client = ApiClient("app")
    client.validate(
        _response({"code": 0, "msg": ""}, status=201),
        _case(status_code=[200, 201]),
    )


def test_elapsed_timeout_is_skipped_after_first_hit():
    client = ApiClient("app")
    client.spec["max_elapsed_sec"] = 0.2
    slow = _response({"code": 0, "msg": ""}, elapsed=0.5, url="http://127.0.0.1:8765/api/slow")
    case = _case(url="/api/slow")
    with pytest.raises(ResponseTimeout, match="响应时间超时"):
        client.validate(slow, case)
    client.validate(slow, case)


def test_no_token_header_is_omitted(monkeypatch):
    captured = {}

    def fake_request(**kwargs):
        captured.update(kwargs)
        return _response({"code": 0, "msg": "", "data": {}})

    monkeypatch.setattr(ApiClient.session, "request", fake_request)
    ApiClient("app").request(
        {
            "title": "匿名",
            "request": {
                "method": "GET",
                "url": "/api/posts",
                "headers": {"token": "no_token"},
                "params": {},
                "validate": {"status_code": 200, "code": 0, "msg": ""},
            },
        }
    )
    assert "token" not in captured["headers"]
    assert captured["headers"]["ctype"] == "1"
    assert "params" in captured
    assert "json" not in captured


def test_token_key_is_injected(monkeypatch):
    captured = {}

    def fake_request(**kwargs):
        captured.update(kwargs)
        return _response({"code": 0, "msg": "", "data": {}})

    monkeypatch.setattr(ApiClient.session, "request", fake_request)
    write_values({"app_token": "demo-token"})
    ApiClient("app").request(
        {
            "title": "带登录态",
            "request": {
                "method": "POST",
                "url": "/api/posts",
                "headers": {"token": "app_token"},
                "params": {"userId": "${user_id}"},
                "validate": {"status_code": 200, "code": 0, "msg": ""},
            },
        }
    )
    assert captured["headers"]["token"] == "demo-token"
    assert captured["json"]["userId"] == config.ENV_IDS["user_id"]
    assert "params" not in captured
