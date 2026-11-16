"""Explicit local API benchmark. No GPU workload is started by importing this module."""

import concurrent.futures
import contextlib
import datetime
import fcntl
import http.client
import json
import math
import platform
import socket
import statistics
import sys
import threading
import time
import uuid

from . import __version__, readiness
from .common import atomic_json, fingerprint
from .profiles import legacy_model_identity
from .warmup import option


class Transport:
    """Local HTTP only, with a deadline watchdog that also interrupts trickling streams."""

    def __init__(self, spec, timeout):
        self.spec = spec
        self.deadline = time.monotonic() + timeout
        self.lock = threading.Lock()
        self.sockets = set()
        self.cancelled = threading.Event()

    def abort(self):
        self.cancelled.set()
        with self.lock:
            for sock in self.sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def remaining(self):
        seconds = self.deadline - time.monotonic()
        if seconds <= 0 or self.cancelled.is_set():
            raise RuntimeError("Benchmark cancelled or timed out")
        return seconds

    @contextlib.contextmanager
    def response(self, path, payload):
        connection = http.client.HTTPConnection(
            readiness.address(self.spec), self.spec["port"], timeout=min(2, self.remaining())
        )
        sock = None
        try:
            connection.connect()
            sock = connection.sock
            with self.lock:
                self.sockets.add(sock)
            sock.settimeout(self.remaining())
            connection.request(
                "POST", path, json.dumps(payload).encode(), {"Content-Type": "application/json"}
            )
            response = connection.getresponse()
            try:
                if response.status != 200:
                    raise RuntimeError("Benchmark API HTTP %s" % response.status)
                yield response
                self.remaining()
            finally:
                response.close()
        finally:
            connection.close()
            with self.lock:
                self.sockets.discard(sock)

    def tokenize(self, model, text):
        with self.response(
            "/tokenize", {"model": model, "prompt": text, "add_special_tokens": False}
        ) as response:
            body = response.read(1024 * 1024 + 1)
            if len(body) > 1024 * 1024:
                raise RuntimeError("Tokenizer response too large")
            value = json.loads(body)
        tokens = value.get("tokens") if isinstance(value, dict) else None
        if (
            not isinstance(tokens, list)
            or not tokens
            or any(type(n) is not int or n < 0 for n in tokens)
        ):
            raise RuntimeError("Tokenizer did not return token IDs")
        return tokens

    def request(self, model, tokens, output_tokens):
        started = time.monotonic()
        first = None
        usage = None
        finished = done = False
        with self.response(
            "/v1/completions",
            {
                "model": model,
                "prompt": tokens,
                "max_tokens": output_tokens,
                "temperature": 0,
                "ignore_eos": True,
                "add_special_tokens": False,
                "skip_special_tokens": False,
                "stream": True,
                "stream_options": {"include_usage": True},
            },
        ) as response:
            if response.getheader("Content-Type", "").split(";")[0] != "text/event-stream":
                raise RuntimeError("Expected a streaming SSE response")
            size = 0
            while True:
                self.remaining()
                line = response.readline(1024 * 1024 + 1)
                size += len(line)
                if len(line) > 1024 * 1024 or size > 16 * 1024 * 1024:
                    raise RuntimeError("Benchmark stream too large")
                if not line:
                    break
                if not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    done = True
                    break
                value = json.loads(data)
                if not isinstance(value, dict) or value.get("error"):
                    raise RuntimeError("Invalid benchmark stream event")
                choices = value.get("choices", [])
                if not isinstance(choices, list) or any(not isinstance(c, dict) for c in choices):
                    raise RuntimeError("Invalid benchmark stream choices")
                for choice in choices:
                    if not isinstance(choice.get("text", ""), str):
                        raise RuntimeError("Invalid benchmark stream text")
                    if choice.get("text") and first is None:
                        first = time.monotonic() - started
                    if choice.get("finish_reason") is not None:
                        if choice["finish_reason"] != "length":
                            raise RuntimeError("Benchmark generation ended before the token limit")
                        finished = True
                if value.get("usage") is not None:
                    usage = value["usage"]
        elapsed = time.monotonic() - started
        if not done or not finished or first is None:
            raise RuntimeError("Incomplete benchmark stream")
        if (
            not isinstance(usage, dict)
            or type(usage.get("prompt_tokens")) is not int
            or type(usage.get("completion_tokens")) is not int
            or usage["prompt_tokens"] != len(tokens)
            or usage["completion_tokens"] != output_tokens
        ):
            raise RuntimeError("Benchmark API token counts do not match the requested shape")
        return {
            "input_tokens": usage["prompt_tokens"],
            "output_tokens": usage["completion_tokens"],
            "first_chunk_seconds": first,
            "elapsed_seconds": elapsed,
            "output_tokens_per_second": output_tokens / elapsed,
        }


def summary(requests, elapsed):
    def stats(key):
        values = sorted(row[key] for row in requests)
        return {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p95": values[math.ceil(len(values) * 0.95) - 1],
        }

    return {
        "requests": len(requests),
        "elapsed_seconds": elapsed,
        "first_chunk_seconds": stats("first_chunk_seconds"),
        "request_seconds": stats("elapsed_seconds"),
        "request_output_tokens_per_second": stats("output_tokens_per_second"),
        "aggregate_output_tokens_per_second": sum(r["output_tokens"] for r in requests) / elapsed,
    }


def run(
    spec,
    inspect,
    input_tokens=1024,
    output_tokens=256,
    concurrency=1,
    repeats=3,
    warmup_rounds=1,
    timeout=600,
):
    for name, number in {
        "input-tokens": input_tokens,
        "output-tokens": output_tokens,
        "concurrency": concurrency,
        "repeats": repeats,
        "timeout": timeout,
    }.items():
        if number <= 0:
            raise ValueError("--%s must be positive" % name)
    if warmup_rounds < 0:
        raise ValueError("--warmup-rounds must be nonnegative")
    if concurrency > 64:
        raise ValueError("Benchmark concurrency is limited to 64")
    if input_tokens + output_tokens > int(option(spec, "--max-model-len", 32768)):
        raise ValueError("Benchmark input plus output exceeds --max-model-len")
    model = option(spec, "--served-model-name")
    if not model:
        raise ValueError("Benchmark requires a served model name")
    directory = readiness.log_path(spec).parent
    # Share the warmup lock: these two explicit synthetic workloads must not overlap.
    with (directory / ".warmup.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another benchmark or warmup is already running") from error
        return _run(
            spec,
            inspect,
            model,
            input_tokens,
            output_tokens,
            concurrency,
            repeats,
            warmup_rounds,
            timeout,
        )


def _run(spec, inspect, model, inputs, outputs, concurrency, repeats, warmups, timeout):
    current = inspect(spec["container"])
    if not current or not current["State"].get("Running"):
        raise RuntimeError("Benchmark requires a running managed container")
    identity = current["State"].get("StartedAt")
    if not identity:
        raise RuntimeError("Container start identity is missing")
    if not readiness.probe(spec)["ready"]:
        raise RuntimeError("API is not ready; check server status")
    started = time.monotonic()
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    path = readiness.log_path(spec).with_name("benchmark-%s.json" % uuid.uuid4().hex)
    result = {
        "schema_version": 1,
        "state": "running",
        "completed": False,
        "started_at": stamp,
        "version": __version__,
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "spec": spec,
        "spec_fingerprint": fingerprint(spec),
        "container_started_at": identity,
        "container_image_id": current.get("Image"),
        "endpoint": "http://%s:%s/v1" % (readiness.address(spec), spec["port"]),
        "model": model,
        "model_identity": spec.get("model_identity") or legacy_model_identity(),
        "result_path": str(path),
        "suite": {
            "input_tokens": inputs,
            "output_tokens": outputs,
            "concurrency": concurrency,
            "repeats": repeats,
            "warmup_rounds": warmups,
            "timeout_seconds": timeout,
        },
        "method": "synthetic token-ID completions; unique prefixes; no cache reset; "
        "first nonempty text chunk approximates TTFT; rates include full request time; "
        "special/reasoning tokens included; warmup and tokenization excluded from summary",
        "warmup": {"rounds": [], "elapsed_seconds": 0},
        "rounds": [],
    }
    transport = Transport(spec, timeout)
    watchdog = threading.Timer(timeout, transport.abort)
    watchdog.daemon = True
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)

    def save():
        result["elapsed_seconds"] = time.monotonic() - started
        atomic_json(path, result)

    def same_container():
        now = inspect(spec["container"])
        if not now or not now["State"].get("Running") or now["State"].get("StartedAt") != identity:
            raise RuntimeError("Container stopped or restarted during benchmark")

    try:
        save()
        watchdog.start()
        print(
            "BENCHMARK: synthetic inference traffic; avoid other traffic for comparison; "
            "results: " + str(path),
            file=sys.stderr,
            flush=True,
        )
        filler = transport.tokenize(model, " gpu=healthy disk=healthy network=reachable\n")
        for phase, count in (("warmup", warmups), ("measure", repeats)):
            for index in range(count):
                transport.remaining()
                same_container()
                print(
                    "BENCHMARK %s %s/%s: input=%s output=%s concurrency=%s"
                    % (phase, index + 1, count, inputs, outputs, concurrency),
                    file=sys.stderr,
                    flush=True,
                )
                prompts = []
                for _ in range(concurrency):
                    prefix = transport.tokenize(model, uuid.uuid4().hex + " ")
                    missing = max(0, inputs - len(prefix))
                    prompts.append((prefix + filler * math.ceil(missing / len(filler)))[:inputs])
                before = time.monotonic()
                futures = [pool.submit(transport.request, model, p, outputs) for p in prompts]
                # Persist successful requests even when another request in the round fails.
                batch = {"requests": [], "elapsed_seconds": 0}
                target = result["warmup"]["rounds"] if phase == "warmup" else result["rounds"]
                target.append(batch)
                try:
                    for future in concurrent.futures.as_completed(futures, transport.remaining()):
                        batch["requests"].append(future.result())
                finally:
                    batch["elapsed_seconds"] = time.monotonic() - before
                    if phase == "warmup":
                        result["warmup"]["elapsed_seconds"] += batch["elapsed_seconds"]
                    save()
                same_container()
                print(
                    "BENCHMARK %s %s/%s complete (%.3fs)"
                    % (phase, index + 1, count, batch["elapsed_seconds"]),
                    file=sys.stderr,
                    flush=True,
                )
        transport.remaining()
        same_container()
        rows = [row for batch in result["rounds"] for row in batch["requests"]]
        result["summary"] = summary(rows, sum(b["elapsed_seconds"] for b in result["rounds"]))
        result.update(state="completed", completed=True)
        save()
        measured = result["summary"]
        print(
            "BENCHMARK COMPLETE: first chunk mean %.3fs; request mean %.3fs; "
            "per-request mean %.2f output tokens/s; aggregate %.2f output tokens/s; results: %s"
            % (
                measured["first_chunk_seconds"]["mean"],
                measured["request_seconds"]["mean"],
                measured["request_output_tokens_per_second"]["mean"],
                measured["aggregate_output_tokens_per_second"],
                path,
            ),
            file=sys.stderr,
            flush=True,
        )
        return result
    except BaseException as error:
        detail = str(error) or type(error).__name__
        if not isinstance(error, KeyboardInterrupt) and time.monotonic() >= transport.deadline:
            detail = "Benchmark timed out after %ss" % timeout
        transport.abort()
        result.update(
            state="cancelled" if isinstance(error, KeyboardInterrupt) else "failed",
            completed=False,
            error=detail,
        )
        result.pop("summary", None)
        save()
        if isinstance(error, KeyboardInterrupt):
            print("BENCHMARK CANCELLED; results: " + str(path), file=sys.stderr, flush=True)
            raise
        raise RuntimeError(
            "Benchmark failed; container left running; see %s: %s" % (path, result["error"])
        ) from error
    finally:
        watchdog.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
