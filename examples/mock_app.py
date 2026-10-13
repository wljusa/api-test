# -*- coding: utf-8 -*-
"""本地示例服务，返回 {code, msg, data}。不依赖外网。"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Tuple
from urllib.parse import parse_qs, urlparse


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/posts":
            if not self._authorized():
                self._json({"code": 10016, "msg": "未登录", "data": None})
                return
            self._json(
                {
                    "code": 0,
                    "msg": "",
                    "data": {"list": [{"id": 1, "title": "hello"}], "total": 1},
                }
            )
            return
        if parsed.path == "/api/profile":
            if not self._authorized():
                self._json({"code": 10016, "msg": "未登录", "data": None})
                return
            raw_id = (query.get("userId") or ["0"])[0]
            self._json(
                {
                    "code": 0,
                    "msg": "",
                    "data": {"userId": int(raw_id), "name": "demo"},
                }
            )
            return
        self._json({"code": 404, "msg": "not found", "data": None}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/login":
            self._json({"code": 404, "msg": "not found", "data": None}, status=404)
            return
        body = self._read_json()
        if body.get("username") == "demo" and body.get("password") == "demo":
            self._json({"code": 0, "msg": "", "data": {"token": "demo-token"}})
            return
        self._json({"code": 40001, "msg": "账号或密码错误", "data": None})

    def _authorized(self) -> bool:
        return self.headers.get("token") == "demo-token"

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ReuseServer(ThreadingHTTPServer):
    allow_reuse_address = True


def parse_base_url(base_url: str) -> Tuple[str, int]:
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def create_server(base_url: str) -> ReuseServer:
    host, port = parse_base_url(base_url)
    try:
        return ReuseServer((host, port), Handler)
    except OSError as exc:
        raise OSError("无法在 %s:%s 启动示例服务: %s" % (host, port, exc)) from exc
