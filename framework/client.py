# -*- coding: utf-8 -*-
"""按客户端配置发请求，并在这里集中做响应断言。"""
import copy
import json
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

import allure
import requests

import config
from framework.case_loader import resolve_params
from framework.store import read_value, write_values


class ResponseTimeout(AssertionError):
    """响应耗时超过客户端上限。业务断言失败仍使用 AssertionError。"""

    def __init__(self, message: str, response: Any = None):
        super().__init__(message)
        self.response = response


class ApiClient:
    session = requests.Session()
    _elapsed_checked_keys: set = set()

    def __init__(self, name: str):
        if name not in config.CLIENTS:
            raise KeyError("未配置客户端: %s" % name)
        spec = config.CLIENTS[name]
        self.name = name
        self.spec = dict(spec)
        self.spec["headers"] = dict(spec.get("headers") or {})

    @classmethod
    def reset_elapsed_checked(cls) -> None:
        cls._elapsed_checked_keys.clear()

    def base_url(self) -> str:
        return str(self.spec["base_url"]).rstrip("/")

    def request(
        self,
        casedata: dict,
        *,
        validate: bool = True,
        before_validate: Optional[Callable] = None,
    ) -> requests.Response:
        case = copy.deepcopy(casedata)
        self._apply_labels(case)
        prepared = case["request"]
        resolve_params(prepared.get("params"))
        resolve_params(prepared.get("headers"))
        resolve_params(prepared.get("validate"))

        method = str(prepared["method"]).upper()
        url = self.base_url() + _normalize_path(prepared["url"])
        headers = self._build_headers(prepared.get("headers"))
        params = prepared.get("params")

        call = {"method": method, "url": url, "headers": headers}
        if method in ("GET", "DELETE", "HEAD"):
            if params is not None:
                call["params"] = params
        elif params is not None:
            call["json"] = params

        response = self.session.request(**call)
        _print_exchange(response)
        if before_validate is not None:
            before_validate(response)
        if validate:
            self.validate(response, case)
        else:
            _attach_exchange(response)
        return response

    def login(self, casedata: dict, token_key: Optional[str] = None) -> requests.Response:
        key = token_key or self.spec.get("token_key") or "token"

        def _save(response: requests.Response) -> None:
            token_value = _extract_token(response)
            if token_value and key:
                write_values({key: token_value})

        return self.request(casedata, before_validate=_save)

    def validate(self, response: requests.Response, casedata: dict) -> None:
        prepared = casedata["request"]
        validate_cfg = prepared.get("validate") or {}
        errors = []
        api_key = _api_key(self.name, prepared.get("method"), prepared.get("url"))
        check_elapsed = self._should_check_elapsed(api_key)

        expected_status = validate_cfg.get("status_code")
        if expected_status is not None and not _status_ok(response.status_code, expected_status):
            errors.append(
                "预期状态码: %s, 实际状态码: %s" % (expected_status, response.status_code)
            )

        if validate_cfg.get("empty_body"):
            if response.text.strip():
                errors.append("预期空响应体, 实际: %s" % response.text[:200])
            self._finish(response, errors, api_key, check_elapsed)
            return

        needs_body = "code" in validate_cfg or "code_not" in validate_cfg
        if not needs_body:
            self._finish(response, errors, api_key, check_elapsed)
            return

        try:
            response_data = response.json()
        except ValueError:
            errors.append("响应不是 JSON")
            self._finish(response, errors, api_key, check_elapsed)
            return

        if not isinstance(response_data, dict):
            errors.append("响应 JSON 必须是对象")
            self._finish(response, errors, api_key, check_elapsed)
            return

        actual_code = response_data.get("code")
        excluded = validate_cfg.get("code_not")
        if excluded is not None:
            if _code_equal(excluded, actual_code):
                errors.append("预期 code 不在 %s 中, 实际 code: %s" % (excluded, actual_code))
        else:
            expected_code = validate_cfg.get("code")
            if expected_code is not None and not _code_equal(expected_code, actual_code):
                errors.append("预期 code: %s, 实际 code: %s" % (expected_code, actual_code))

        if "msg" in validate_cfg and not _msg_equal(validate_cfg.get("msg"), response_data.get("msg")):
            errors.append(
                "预期 msg: %s, 实际 msg: %s" % (validate_cfg.get("msg"), response_data.get("msg"))
            )

        expected_fields = validate_cfg.get("expected_fields") or []
        if expected_fields and _code_equal(0, actual_code):
            missing = [
                field
                for field in expected_fields
                if not has_field(response_data, field)
            ]
            if missing:
                errors.append("响应中缺少字段: %s" % ", ".join(missing))

        expected_data = validate_cfg.get("expected_data") or {}
        if expected_data and _code_equal(0, actual_code):
            data_block = response_data.get("data")
            if not isinstance(data_block, dict):
                errors.append("预期 data 为对象, 实际: %s" % type(data_block).__name__)
            else:
                for field, expected_val in expected_data.items():
                    actual_val = data_block.get(field)
                    if isinstance(expected_val, (list, dict)):
                        matched = expected_val == actual_val
                    else:
                        matched = _code_equal(expected_val, actual_val)
                    if not matched:
                        errors.append(
                            "data.%s 预期: %s, 实际: %s" % (field, expected_val, actual_val)
                        )

        forbidden = list(validate_cfg.get("forbidden_fields") or [])
        if forbidden:
            violations = find_forbidden_violations(response_data, forbidden)
            if violations:
                url = getattr(response, "url", "") or ""
                errors.append(
                    "响应中包含禁止返回的字段: %s, url=%s"
                    % (format_forbidden(violations), url)
                )

        self._finish(response, errors, api_key, check_elapsed)

    def _should_check_elapsed(self, api_key: tuple) -> bool:
        if api_key in self._elapsed_checked_keys:
            return False
        return self.spec.get("max_elapsed_sec") is not None

    def _finish(
        self,
        response: requests.Response,
        errors: list,
        api_key: tuple,
        check_elapsed: bool,
    ) -> None:
        limit = self.spec.get("max_elapsed_sec") if check_elapsed else None
        timed_out = False
        if limit is not None and response is not None:
            elapsed = response.elapsed.total_seconds()
            if elapsed > float(limit):
                timed_out = True
                url = getattr(response, "url", "") or ""
                errors.append(
                    "响应时间超时: %.2fs > %.2fs (客户端=%s), url=%s"
                    % (elapsed, float(limit), self.name, url)
                )
        if check_elapsed and timed_out:
            self._elapsed_checked_keys.add(api_key)
        if not errors:
            _attach_exchange(response)
            return
        _attach_exchange(response)
        _attach_failure_dump(response)
        timeout_errors = [item for item in errors if item.startswith("响应时间超时")]
        biz_errors = [item for item in errors if not item.startswith("响应时间超时")]
        message = "\n".join(biz_errors + timeout_errors)
        if biz_errors:
            exc = AssertionError(message)
            exc.response = response  # type: ignore[attr-defined]
            raise exc
        raise ResponseTimeout(message, response=response)

    def _build_headers(self, case_headers: Optional[dict]) -> dict:
        headers = dict(self.spec.get("headers") or {})
        headers.update(case_headers or {})
        token_slot = headers.get("token")
        if token_slot == "no_token":
            headers.pop("token", None)
            return headers
        key = token_slot or self.spec.get("token_key")
        if not key:
            return headers
        stored = read_value(str(key))
        headers["token"] = "" if stored is None else stored
        return headers

    @staticmethod
    def _apply_labels(casedata: dict) -> None:
        feature = casedata.get("feature")
        story = casedata.get("story")
        title = casedata.get("title")
        if feature:
            allure.dynamic.feature(str(feature))
        if story:
            allure.dynamic.story(str(story))
        if title:
            allure.dynamic.title(str(title))


def _normalize_path(url_path: str) -> str:
    path = str(url_path or "").strip()
    if not path.startswith("/"):
        path = "/" + path
    return path


def _api_key(client_name: str, method: Any, url_path: Any) -> tuple:
    path = _normalize_path(str(url_path or "/"))
    split = urlsplit(path)
    clean = split.path or "/"
    if clean != "/" and clean.endswith("/"):
        clean = clean.rstrip("/")
    return (client_name or "", str(method or "").upper(), clean)


def _status_ok(actual: int, expected: Any) -> bool:
    if isinstance(expected, (list, tuple, set)):
        return actual in expected
    return actual == expected


def _code_equal(expected: Any, actual: Any) -> bool:
    if isinstance(expected, (list, tuple, set)):
        return any(_code_equal(item, actual) for item in expected)
    if expected == actual:
        return True
    try:
        return int(str(expected).strip()) == int(str(actual).strip())
    except (TypeError, ValueError):
        return str(expected) == str(actual)


def _msg_equal(expected: Any, actual: Any) -> bool:
    if isinstance(expected, (list, tuple, set)):
        return any(_msg_equal(item, actual) for item in expected)
    if expected is None:
        return True
    text = str(expected).strip()
    if not text:
        return True
    return str(actual or "").strip() == text


def has_field(data: Any, field: str) -> bool:
    if isinstance(data, dict):
        if field in data:
            return True
        return any(has_field(value, field) for value in data.values())
    if isinstance(data, list):
        return any(has_field(item, field) for item in data)
    return False


def _sensitive(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    return True


def _field_paths(data: Any, field: str, prefix: str = "") -> list:
    found = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = "%s.%s" % (prefix, key) if prefix else key
            if key == field:
                found.append((path, value))
            found.extend(_field_paths(value, field, path))
    elif isinstance(data, list):
        for index, item in enumerate(data):
            found.extend(_field_paths(item, field, "%s[%s]" % (prefix, index)))
    return found


def find_forbidden_violations(data: Any, fields: list) -> list:
    violations = []
    for field in fields:
        for path, value in _field_paths(data, field):
            if _sensitive(value):
                violations.append((field, path, value))
    return violations


def format_forbidden(violations: list, max_samples: int = 3) -> str:
    grouped: dict = {}
    for field, path, value in violations:
        grouped.setdefault(field, []).append((path, value))
    parts = []
    for field, items in grouped.items():
        samples = ", ".join("%s=%r" % (path, val) for path, val in items[:max_samples])
        if len(items) > max_samples:
            samples = "%s 等%s处" % (samples, len(items))
        parts.append("%s (%s)" % (field, samples))
    return "; ".join(parts)


def _extract_token(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = {}
    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, dict) and data.get("token"):
        return str(data["token"])
    cookie_token = response.cookies.get("token") if response.cookies is not None else None
    if cookie_token:
        return str(cookie_token)
    header_token = response.headers.get("token") if response.headers is not None else None
    return str(header_token or "")


def _print_exchange(response: requests.Response) -> None:
    request = response.request
    print("\nurl===>", request.url)
    print("method===>", request.method)
    print("status_code===>", response.status_code)
    print("body===>", request.body)
    print("headers===>", request.headers)
    try:
        print("response===>", response.json())
    except ValueError:
        print("response===>", response.text[:500])


def _attach_exchange(response: requests.Response) -> None:
    request = response.request
    payload = {
        "url": request.url,
        "method": request.method,
        "headers": dict(request.headers),
    }
    if request.body:
        payload["body"] = _decode_body(request.body)
    allure.attach(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        name="Request Info",
        attachment_type=allure.attachment_type.JSON,
    )
    try:
        allure.attach(
            json.dumps(response.json(), indent=2, ensure_ascii=False),
            name="Response Content",
            attachment_type=allure.attachment_type.JSON,
        )
    except ValueError:
        allure.attach(
            response.text,
            name="Response Text",
            attachment_type=allure.attachment_type.TEXT,
        )


def _decode_body(body: Any) -> Any:
    if isinstance(body, bytes):
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return repr(body)
        try:
            return json.loads(text)
        except ValueError:
            return text
    return body


def _attach_failure_dump(response: requests.Response) -> None:
    request = response.request
    try:
        resp_text = json.dumps(response.json(), ensure_ascii=False)
    except ValueError:
        resp_text = response.text or ""
        if len(resp_text) > 8000:
            resp_text = resp_text[:8000] + "...(truncated)"
    dump = "URL: %s %s\nHeader: %s\n参数: %s\n响应: %s" % (
        request.method,
        request.url,
        dict(request.headers),
        _decode_body(request.body),
        resp_text,
    )
    allure.attach(dump, name="请求详情", attachment_type=allure.attachment_type.TEXT)
