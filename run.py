# -*- coding: utf-8 -*-
"""pytest 入口。生成 Allure 报告需要本机已安装 allure 命令行。"""
import os
import shutil
import sys

import pytest


if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    code = pytest.main(["-v", "--rootdir=%s" % root, "tests", "examples"])
    if shutil.which("allure"):
        os.system(
            "allure generate ./report/allure-results -o ./report/allure-report --clean"
        )
    else:
        print("未安装 allure 命令行，跳过 HTML 报告。原始结果在 report/allure-results")
    sys.exit(code)
