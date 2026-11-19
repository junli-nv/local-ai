"""Read and summarize vLLM Prometheus metrics from the client."""

import math
import re
import sys
import time
import urllib.request
from datetime import datetime
from http.client import HTTPException
from urllib.parse import urlsplit

from .endpoint import endpoint_url

RUNNING = "num_requests_running"
WAITING = "num_requests_waiting"
KV = "kv_cache_usage_perc"
PREEMPTIONS = "num_preemptions"
HITS = "prefix_cache_hits"
QUERIES = "prefix_cache_queries"
QUEUE_TIME = "request_queue_time_seconds"
FIRST_TOKEN = "time_to_first_token_seconds"
GAUGES = (RUNNING, WAITING, KV)
METRICS = {
    *GAUGES,
    *(f"{name}{suffix}" for name in (PREEMPTIONS, HITS, QUERIES) for suffix in ("", "_total")),
    *(f"{name}_bucket" for name in (QUEUE_TIME, FIRST_TOKEN)),
}
SAMPLE = re.compile(r'^vllm:(\w+)(?:\{((?:[^"}]|"(?:\\.|[^"\\])*")*)\})?\s+(\S+)')
LABEL = re.compile(r'(\w+)="((?:\\.|[^"\\])*)"')


MESSAGES = {
    "unavailable": ("Unavailable", "不可用"),
    "few": ("Too few samples ({count:g})", "样本不足（{count:g} 个）"),
    "bound": (
        "{operator} {bound:g} s ({count:g} observations)",
        "{operator} {bound:g} 秒（{count:g} 个）",
    ),
    "finished": (
        "Sampling complete · {ok}/{count} successful · {elapsed:.1f} s",
        "采样结束 · {ok}/{count} 次成功 · {elapsed:.1f} 秒",
    ),
    "queue": (
        "Queue       Waiting in {busy} of {count} samples, empty in {empty}. Highest observed queue: {peak:g}.",
        "排队情况   {count} 次有效采样中有 {busy} 次排队、{empty} 次队列为空；采样时最多 {peak:g} 个等待。",
    ),
    "latency": (
        "Latency     Median queue time: {queue}. Median server time to first token: {first}.",
        "请求耗时   排队中位数 {queue}；服务端首 token 中位数 {first}。",
    ),
    "cache": (
        "KV cache    Peak observed usage: {peak}. New preemptions: {extra}.",
        "缓存情况   采样时 KV 缓存池最高 {peak}；窗口内新增抢占 {extra}。",
    ),
    "events": ("{count:g}", "{count:g} 次"),
    "no_queries": ("No queries in this window", "无查询样本"),
    "prefix": (
        "Prefix cache  Token hit rate during sampling: {ratio}.",
        "前缀缓存   窗口内 token 命中率 {ratio}。",
    ),
    "endpoint": (
        "Specify --endpoint or save a default with local-ai config set endpoint URL",
        "请用 --endpoint 指定地址，或用 local-ai config set endpoint URL 设置默认值",
    ),
    "arguments": (
        "--count must be a positive integer and --interval must be a finite positive number",
        "--count 必须是正整数，--interval 必须是有限正数",
    ),
    "schedule": (
        "Sampling every {interval:g} s, {count} samples",
        "每 {interval:g} 秒采样一次，共 {count} 次",
    ),
    "header": (
        "Time          Running   Waiting   KV cache usage",
        "时间       运行中   排队中   KV 缓存池使用率",
    ),
    "no_metrics": (
        "Response contains no usable vLLM load metrics",
        "响应中没有可用的 vLLM 负载指标",
    ),
    "failed": ("Sample failed", "采样失败"),
    "failure": (
        "Sample {index}/{count} failed ({url}): {error}",
        "{index}/{count} 采样失败（{url}）：{error}",
    ),
    "waiting_help": (
        "How to read  Waiting is the queue size at sample time. Queue time measures how long requests waited.",
        "怎么看     排队中是采样时等待调度的请求数；排队耗时是请求等了多久。",
    ),
    "kv_help": (
        "             KV usage is cache-pool occupancy. With multiple engines, the highest value is shown.",
        "           KV 使用率表示缓存池用了多少；有多个引擎时显示最高值。",
    ),
    "missing_help": (
        "             — means the metric is missing.",
        "           — 表示该指标未提供。",
    ),
    "pressure_help": (
        "             Persistent queues, high KV usage and new preemptions together point to possible cache pressure.",
        "           若多次都在排队，同时 KV 使用率高且抢占增加，可检查缓存容量。",
    ),
    "prefix_help": (
        "             Preemption pauses a running request to free resources. Prefix hits measure reuse of queried tokens.",
        "           抢占是运行中的请求暂时让出资源；前缀命中率越高，复用的前缀 token 比例越高。",
    ),
}


def message(lang, key, **values):
    return MESSAGES[key][lang == "zh"].format(**values)


def parse_metrics(body):
    samples = {}
    for line in body.splitlines():
        match = SAMPLE.match(line)
        if not match or match[1] not in METRICS:
            continue
        try:
            value = float(match[3])
        except ValueError:
            continue
        if math.isfinite(value) and value >= 0 and (match[1] != KV or value <= 1):
            labels = tuple(sorted(LABEL.findall(match[2] or "")))
            samples.setdefault(match[1], {})[labels] = value
    return samples


def fetch(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        body = response.read(8 * 1024 * 1024 + 1)
    if len(body) > 8 * 1024 * 1024:
        raise ValueError("Metrics response exceeds 8 MiB")
    return parse_metrics(body.decode("utf-8"))


def gauge(snapshot, name):
    values = snapshot.get(name, {}).values()
    if not values:
        return None
    return max(values) if name == KV else sum(values)


def series(snapshot, name):
    return snapshot.get(name + "_total", snapshot.get(name, {}))


def changes(window, name):
    if len(window) < 2 or any(snapshot is None for snapshot in window):
        return None
    samples = [series(snapshot, name) for snapshot in window]
    first = samples[0]
    if not first:
        return None
    for before, after in zip(samples, samples[1:]):
        if before.keys() != after.keys() or any(after[key] < before[key] for key in before):
            return None
    return {key: samples[-1][key] - first[key] for key in first}


def median(window, metric, lang="en"):
    buckets = changes(window, metric + "_bucket")
    if buckets is None:
        return message(lang, "unavailable")
    histograms = {}
    for labels, count in buckets.items():
        upper = dict(labels).get("le")
        try:
            bound = float(upper)
        except (TypeError, ValueError):
            return message(lang, "unavailable")
        if math.isnan(bound) or bound < 0:
            return message(lang, "unavailable")
        key = tuple((label, value) for label, value in labels if label != "le")
        histograms.setdefault(key, {})[bound] = count
    limits = sorted(next(iter(histograms.values())))
    if limits[-1] != math.inf or any(sorted(row) != limits for row in histograms.values()):
        return message(lang, "unavailable")
    totals = [sum(row[bound] for row in histograms.values()) for bound in limits]
    if any(after < before for before, after in zip(totals, totals[1:])):
        return message(lang, "unavailable")
    count = totals[-1]
    if count < 5:
        return message(lang, "few", count=count)
    bound = next(bound for bound, total in zip(limits, totals) if total >= count / 2)
    if math.isinf(bound):
        if len(limits) == 1:
            return message(lang, "unavailable")
        return message(lang, "bound", operator=">", bound=limits[-2], count=count)
    return message(lang, "bound", operator="≤", bound=bound, count=count)


def summarize(window, elapsed, lang):
    snapshots = [snapshot for snapshot in window if snapshot is not None]
    print("\n" + message(lang, "finished", ok=len(snapshots), count=len(window), elapsed=elapsed))
    waiting = [value for row in snapshots if (value := gauge(row, WAITING)) is not None]
    kv = [value for row in snapshots if (value := gauge(row, KV)) is not None]
    if waiting:
        busy = sum(value > 0 for value in waiting)
        print(
            message(
                lang,
                "queue",
                count=len(waiting),
                busy=busy,
                empty=len(waiting) - busy,
                peak=max(waiting),
            )
        )
    print(
        message(
            lang,
            "latency",
            queue=median(window, QUEUE_TIME, lang),
            first=median(window, FIRST_TOKEN, lang),
        )
    )
    unavailable = message(lang, "unavailable")
    preemptions = changes(window, PREEMPTIONS)
    peak = f"{max(kv):.0%}" if kv else unavailable
    extra = (
        message(lang, "events", count=sum(preemptions.values()))
        if preemptions is not None
        else unavailable
    )
    print(message(lang, "cache", peak=peak, extra=extra))
    hits, queries = changes(window, HITS), changes(window, QUERIES)
    if hits is None or queries is None or hits.keys() != queries.keys():
        ratio = unavailable
    elif any(hits[key] > queries[key] for key in hits):
        ratio = unavailable
    elif sum(queries.values()) == 0:
        ratio = message(lang, "no_queries")
    else:
        ratio = f"{sum(hits.values()) / sum(queries.values()):.0%}"
    print(message(lang, "prefix", ratio=ratio))


def probe(endpoint, interval, count, lang="en"):
    if not endpoint:
        raise ValueError(
            "请用 --endpoint 指定地址，或用 local-ai config set endpoint URL 设置默认值"
        )
    if count < 1 or not math.isfinite(interval) or interval <= 0:
        raise ValueError(message(lang, "arguments"))
    base = endpoint_url(endpoint)
    url = base.removesuffix("/v1") + "/metrics"
    print(urlsplit(base).netloc)
    if count > 1:
        print(message(lang, "schedule", interval=interval, count=count))
    print("\n" + message(lang, "header"), flush=True)

    window = []
    start = time.monotonic()
    next_sample = start
    for index in range(count):
        if index:
            time.sleep(max(0, next_sample - time.monotonic()))
        next_sample = time.monotonic() + interval
        try:
            snapshot = fetch(url)
            if not any(snapshot.get(metric) for metric in GAUGES):
                raise ValueError(message(lang, "no_metrics"))
        except (OSError, ValueError, HTTPException) as error:
            snapshot = None
            print(
                message(lang, "failure", index=index + 1, count=count, url=url, error=error),
                file=sys.stderr,
                flush=True,
            )
        window.append(snapshot)
        now = datetime.now().strftime("%H:%M:%S")
        if snapshot is None:
            print(f"{now}   " + message(lang, "failed"), flush=True)
            continue
        running, waiting, kv = (gauge(snapshot, metric) for metric in GAUGES)
        running_text = f"{running:g}" if running is not None else "—"
        waiting_text = f"{waiting:g}" if waiting is not None else "—"
        kv_text = f"{kv:.0%}" if kv is not None else "—"
        print(f"{now}   {running_text:>6}   {waiting_text:>6}   {kv_text:>15}", flush=True)

    if count > 1:
        summarize(window, time.monotonic() - start, lang)
    print("\n" + message(lang, "waiting_help"))
    print(message(lang, "kv_help"))
    print(message(lang, "missing_help"))
    if count > 1:
        print(message(lang, "pressure_help"))
        print(message(lang, "prefix_help"))
    return 0 if all(snapshot is not None for snapshot in window) else 1
