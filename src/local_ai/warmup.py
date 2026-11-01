"""Explicit, bounded inference warmup; health/status queries never generate tokens."""

import concurrent.futures
import datetime
import fcntl
import http.client
import json
import socket
import threading
import time
import uuid

from . import readiness
from .common import atomic_json, fingerprint


def numbers(value):
    try:
        result = list(dict.fromkeys(int(x.strip()) for x in value.split(",")))
    except (ValueError, AttributeError) as error:
        raise ValueError("Expected comma-separated positive integers") from error
    if not result or any(x <= 0 for x in result):
        raise ValueError("Expected comma-separated positive integers")
    return result


def option(spec, flag, default=None):
    args = spec["args"]
    return args[args.index(flag) + 1] if flag in args else default


def suite(spec, inputs=None, concurrency=None, output_tokens=256, repeats=2):
    if output_tokens <= 0 or repeats <= 0:
        raise ValueError("Warmup output tokens and repeats must be positive")
    maximum = int(option(spec, "--max-model-len", 32768))
    if output_tokens >= maximum:
        raise ValueError("Warmup output must be smaller than --max-model-len")
    lengths = (
        numbers(inputs)
        if inputs is not None
        else [n for n in (1024, 8192, 32768) if n + output_tokens <= maximum]
    )
    if not lengths:
        lengths = [maximum - output_tokens]
    if any(n + output_tokens > maximum for n in lengths):
        raise ValueError("Warmup input plus output exceeds --max-model-len")
    limit = int(option(spec, "--max-num-seqs", 4))
    batches = (
        numbers(concurrency)
        if concurrency is not None
        else list(dict.fromkeys(min(n, 2 * limit) for n in (1, 2, 4, 8)))
    )
    return {
        "input_tokens": lengths,
        "concurrency": batches,
        "output_tokens": output_tokens,
        "repeats": repeats,
        "requests": sum(batches) * len(lengths) * repeats,
    }


def progress(spec, container):
    path = readiness.log_path(spec).with_name("warmup.json")
    if not path.is_file():
        return {"state": "not-run", "completed": False}
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError("Invalid warmup record")
        started = container.get("State", {}).get("StartedAt")
        if (
            not container.get("State", {}).get("Running")
            or not started
            or value.get("container_started_at") != started
            or value.get("spec_fingerprint") != fingerprint(spec)
        ):
            return {"state": "stale", "completed": False}
        value["completed"] = value.get("state") == "completed"
        return value
    except (OSError, ValueError):
        return {"state": "invalid", "completed": False}


class Transport:
    def __init__(self, spec, deadline):
        self.spec, self.deadline = spec, deadline
        self.connections = set()
        self.lock = threading.Lock()
        self.cancelled = threading.Event()

    def abort(self):
        self.cancelled.set()
        with self.lock:
            connections = list(self.connections)
        for connection in connections:
            if connection.sock is not None:
                try:
                    connection.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def post(self, path, payload):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0 or self.cancelled.is_set():
            raise RuntimeError("Warmup cancelled or timed out")
        connection = http.client.HTTPConnection(
            readiness.address(self.spec), self.spec["port"], timeout=min(2, remaining)
        )
        with self.lock:
            self.connections.add(connection)
        try:
            connection.connect()
            if self.cancelled.is_set():
                raise RuntimeError("Warmup cancelled")
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Warmup timed out")
            connection.sock.settimeout(remaining)
            connection.request(
                "POST",
                path,
                body=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise RuntimeError("Warmup API response too large")
            if response.status != 200:
                raise RuntimeError(
                    "Warmup API HTTP %s: %s"
                    % (response.status, body[:512].decode(errors="replace"))
                )
            result = json.loads(body)
            if not isinstance(result, dict) or result.get("error"):
                raise RuntimeError("Invalid warmup API response")
            return result
        finally:
            connection.close()
            with self.lock:
                self.connections.discard(connection)


def run(spec, inspect, timeout=600, inputs=None, concurrency=None, output_tokens=256, repeats=2):
    if timeout <= 0:
        raise ValueError("Warmup timeout must be positive")
    shapes = suite(spec, inputs, concurrency, output_tokens, repeats)
    path = readiness.log_path(spec).with_name("warmup.json")
    lock_path = path.with_name(".warmup.lock")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another warmup is already running for this instance") from error
        return _run(spec, inspect, timeout, shapes, path)


def _run(spec, inspect, timeout, shapes, path):
    started = time.monotonic()
    deadline = started + timeout
    current = inspect(spec["container"])
    if current is None or not current["State"].get("Running"):
        raise RuntimeError("Warmup requires a running managed container")
    identity = current["State"].get("StartedAt")
    if not identity:
        raise RuntimeError("Container start identity is missing")
    if not readiness.probe(spec)["ready"]:
        raise RuntimeError("API is not ready; wait for server start or check server status")
    model = option(spec, "--served-model-name")
    if not model:
        raise ValueError("Warmup requires a served model name in instance args")
    value = {
        "state": "running",
        "completed": False,
        "spec_fingerprint": fingerprint(spec),
        "container_started_at": identity,
        "suite": shapes,
        "completed_requests": 0,
        "started_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "batches": [],
    }
    transport = Transport(spec, deadline)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(shapes["concurrency"]))

    def save():
        value["elapsed_seconds"] = round(time.monotonic() - started, 3)
        atomic_json(path, value)

    def same_container():
        now = inspect(spec["container"])
        if (
            now is None
            or not now["State"].get("Running")
            or now["State"].get("StartedAt") != identity
        ):
            raise RuntimeError("Container stopped or restarted during warmup")

    def tokenize(text):
        result = transport.post(
            "/tokenize",
            {
                "model": model,
                "prompt": text,
                "add_special_tokens": False,
            },
        )
        tokens = result.get("tokens")
        if (
            not isinstance(tokens, list)
            or not tokens
            or any(type(x) is not int or x < 0 for x in tokens)
        ):
            raise RuntimeError("Tokenizer API did not return token IDs")
        return tokens

    def request(tokens):
        before = time.monotonic()
        result = transport.post(
            "/v1/completions",
            {
                "model": model,
                "prompt": tokens,
                "max_tokens": shapes["output_tokens"],
                "temperature": 1.0,
                "top_p": 0.95,
                "ignore_eos": True,
                "stream": False,
                "add_special_tokens": False,
            },
        )
        usage = result.get("usage") or {}
        if (
            usage.get("prompt_tokens") != len(tokens)
            or usage.get("completion_tokens") != shapes["output_tokens"]
        ):
            raise RuntimeError("Warmup API token counts do not match the requested shape")
        return time.monotonic() - before

    try:
        save()
        readiness.record(
            spec,
            "正在进行推理预热（WARMING）：%s；会生成合成请求，暂不接受正式流量更利于预热。"
            % shapes,
        )
        filler = tokenize(" node=GPU000 gpu=healthy disk=healthy network=reachable\n")
        nonce = uuid.uuid4().hex
        for repeat in range(shapes["repeats"]):
            for length in shapes["input_tokens"]:
                for count in shapes["concurrency"]:
                    same_container()
                    prefixes = [
                        tokenize("%s %s %s %s %s" % (nonce, repeat, length, count, i))
                        for i in range(count)
                    ]
                    prompts = []
                    for prefix in prefixes:
                        missing = max(0, length - len(prefix))
                        prompts.append(
                            (prefix + filler * ((missing + len(filler) - 1) // len(filler)))[
                                :length
                            ]
                        )
                    futures = [pool.submit(request, prompt) for prompt in prompts]
                    durations = [
                        future.result(timeout=max(0, deadline - time.monotonic()))
                        for future in futures
                    ]
                    value["completed_requests"] += count
                    value["batches"].append(
                        {
                            "input_tokens": length,
                            "concurrency": count,
                            "repeat": repeat + 1,
                            "request_seconds_min": round(min(durations), 3),
                            "request_seconds_max": round(max(durations), 3),
                        }
                    )
                    save()
                    readiness.record(
                        spec,
                        "预热进度（WARMING） %s/%s；input_tokens=%s concurrency=%s repeat=%s；最长请求 %.3fs"
                        % (
                            value["completed_requests"],
                            shapes["requests"],
                            length,
                            count,
                            repeat + 1,
                            max(durations),
                        ),
                    )
        same_container()
        value.update(state="completed", completed=True)
        save()
        readiness.record(
            spec,
            "推理预热完成（WARMUP COMPLETE）；仅覆盖记录的输入长度和并发，新形状仍可能触发 JIT；记录："
            + str(path),
        )
        return value
    except BaseException as error:
        transport.abort()
        value.update(
            state="cancelled" if isinstance(error, KeyboardInterrupt) else "failed",
            completed=False,
            error=str(error) or type(error).__name__,
        )
        save()
        readiness.record(
            spec,
            "推理预热未完成（WARMUP INCOMPLETE）；容器未停止；%s；记录：%s"
            % (value["error"], path),
        )
        if isinstance(error, KeyboardInterrupt):
            raise
        raise RuntimeError(
            "Warmup failed; container left running; see %s: %s" % (path, value["error"])
        ) from error
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
