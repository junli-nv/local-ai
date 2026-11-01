"""Explicit API readiness reporting; no inference requests or container mutation."""

import datetime
import socket
import time
import urllib.request
from pathlib import Path

from . import installlog


def log_path(spec):
    return Path(spec["data_dir"]) / "instances" / spec["instance"] / "server.log"


def address(spec):
    host = spec.get("host", "127.0.0.1")
    return "127.0.0.1" if host == "0.0.0.0" else host


def probe(spec):
    host, port = address(spec), spec["port"]
    health = "http://%s:%d/health" % (host, port)
    value = {"ready": False, "listening": False, "health": health, "detail": ""}
    try:
        with socket.create_connection((host, port), timeout=1):
            value["listening"] = True
    except OSError as error:
        value["detail"] = "端口尚未监听 / port not listening: " + str(error)
        return value
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(health, timeout=2) as response:
            code = response.status
        if code != 200:
            value["detail"] = "API health HTTP %s" % code
            return value
    except OSError as error:
        value["detail"] = "API 尚未就绪 / API not ready: " + str(error)
        return value
    value.update(ready=True, detail="API health HTTP 200")
    return value


def message(value):
    if value["ready"]:
        return "服务已就绪（READY）： " + value["health"] + "，HTTP 200"
    return "服务尚未就绪（NOT READY）： " + value["detail"]


def record(spec, text):
    path = log_path(spec)
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as stream:
        stream.write("\n%s [local-ai] %s\n" % (stamp, text))
    installlog.event(text)


def wait(spec, inspect, timeout=600):
    if timeout <= 0:
        raise ValueError("wait timeout must be positive")
    started = time.monotonic()
    deadline = started + timeout
    next_report = started
    path = log_path(spec)
    record(spec, "正在检查服务就绪状态（CHECKING）；模型加载和编译可能需要数分钟。")
    while True:
        now = time.monotonic()
        if now >= next_report:
            container = inspect(spec["container"])
            if container is None or not container["State"].get("Running"):
                state = container["State"] if container else {}
                text = (
                    "服务启动失败（FAILED）：容器已退出或不存在；exit=%s，OOMKilled=%s；日志：%s"
                    % (state.get("ExitCode"), state.get("OOMKilled"), path)
                )
                record(spec, text)
                raise RuntimeError(text)
        value = probe(spec)
        if value["ready"]:
            current = inspect(spec["container"])
            if current is None or not current["State"].get("Running"):
                text = "服务启动失败（FAILED）：API 响应时容器已退出；日志：%s" % path
                record(spec, text)
                raise RuntimeError(text)
            text = message(value)
            record(spec, text)
            return dict(value, state="ready", log=str(path), message=text)
        if now >= next_report:
            installlog.event(message(value) + "；已等待 %.0f 秒；日志：%s" % (now - started, path))
            next_report = now + 15
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            text = "服务尚未就绪（NOT READY）：等待 %s 秒超时；%s；容器未停止；日志：%s" % (
                timeout,
                value["detail"],
                path,
            )
            record(spec, text)
            raise RuntimeError(text)
        try:
            time.sleep(min(2, remaining))
        except KeyboardInterrupt:
            record(spec, "就绪等待已中断（WAIT CANCELLED）；容器未停止，请用 server status 查询。")
            raise
