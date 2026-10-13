# -*- coding: utf-8 -*-
import pytest

from framework.case_loader import read_env_testcase
from framework.client import ApiClient

_LOGIN = read_env_testcase("login.yaml")
_POSTS = read_env_testcase("posts.yaml")
_PROFILE = read_env_testcase("profile.yaml")


def _ids(cases):
    return [case.get("title", "case") for case in cases]


class TestLogin:
    @pytest.mark.parametrize("data", _LOGIN, ids=_ids(_LOGIN))
    def test_login(self, data):
        ApiClient("app").login(data)


class TestPosts:
    @pytest.mark.usefixtures("app_login")
    @pytest.mark.parametrize("data", _POSTS, ids=_ids(_POSTS))
    def test_posts(self, data):
        """列表场景同时校验字段、禁止字段和响应耗时。"""
        ApiClient("app").request(data)


class TestProfile:
    @pytest.mark.usefixtures("app_login")
    @pytest.mark.parametrize("data", _PROFILE, ids=_ids(_PROFILE))
    def test_profile(self, data):
        ApiClient("app").request(data)
