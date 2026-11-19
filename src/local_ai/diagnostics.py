"""Read-only user diagnostics; no prompts, command arguments or raw output."""

from collections import Counter
from pathlib import Path

from . import execution, history, tasks, telemetry
from .artifacts import validate
from .endpoint import wait_endpoint


def inspect(state_root, assets, endpoint=None, model=None, check_endpoint=False, limit=20):
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be 1..1000")
    state_root = Path(state_root).expanduser().resolve()
    result = {
        "schema": 1,
        "read_only": True,
        "state_root": str(state_root),
        "client": None,
        "histories": [],
        "jobs": [],
        "runs": [],
        "issues": [],
    }
    try:
        result["client"] = {
            k: v for k, v in validate(Path(assets)).items() if k in {"version", "arch", "sha256"}
        }
    except (OSError, ValueError, RuntimeError) as error:
        result["issues"].append({"kind": "client_unavailable", "error_type": type(error).__name__})
    if state_root.exists():
        try:
            result["histories"] = history.list_histories(state_root, endpoint)
        except (OSError, ValueError) as error:
            result["issues"].append(
                {"kind": "history_unreadable", "error_type": type(error).__name__}
            )
        for path in sorted((state_root / "execution/jobs").glob("*/job.json")):
            try:
                job = execution.load(state_root / "execution", path.parent.name)
                value = execution.view(state_root / "execution", job)
                row = {
                    k: value.get(k)
                    for k in [
                        "id",
                        "state",
                        "terminal",
                        "session",
                        "project",
                        "adapter",
                        "controller_running",
                        "output_cache",
                        "exit_code",
                        "output_bytes",
                        "output_truncated",
                        "updated",
                    ]
                }
                if (
                    value.get("adapter")
                    and not value["terminal"]
                    and not value.get("controller_running")
                ):
                    result["issues"].append({"kind": "controller_stopped", "job_id": value["id"]})
                result["jobs"].append(row)
                if value["state"] in {
                    "orphaned",
                    "lost",
                    "unreachable",
                    "unknown",
                    "failed",
                    "output_limit",
                }:
                    result["issues"].append(
                        {
                            "kind": "task_needs_inspection",
                            "job_id": value["id"],
                            "state": value["state"],
                        }
                    )
            except (OSError, ValueError, KeyError) as error:
                result["issues"].append(
                    {
                        "kind": "task_unreadable",
                        "job_id": path.parent.name,
                        "error_type": type(error).__name__,
                    }
                )
        for run in tasks.list_runs(state_root, limit):
            row = {
                k: run.get(k)
                for k in [
                    "run_dir",
                    "state",
                    "sessions",
                    "pending_tools",
                    "exit_code",
                    "endpoint",
                    "model",
                    "client_version",
                ]
            }
            try:
                details = telemetry.report(Path(run["run_dir"]))
                requests = details.get("requests", [])
                row.update(
                    observed_request_count=len(requests),
                    request_observer_enabled=details["run"].get("request_observer_enabled"),
                    api_seconds_sum=details["api_seconds_sum"] if requests else None,
                    observer_ready=details["observer_ready"],
                    malformed_records=details["malformed_records"],
                    context_fraction=details.get("context_fraction"),
                    request_summaries=[
                        {
                            k: r.get(k)
                            for k in [
                                "id",
                                "http_status",
                                "elapsed_seconds",
                                "first_content_seconds",
                                "prompt_tokens",
                                "completion_tokens",
                                "cached_tokens",
                                "complete",
                                "error_type",
                            ]
                        }
                        for r in requests[-50:]
                    ],
                    request_samples_truncated=len(requests) > 50,
                )
            except (OSError, ValueError, KeyError) as error:
                row["request_diagnostics_error"] = type(error).__name__
            result["runs"].append(row)
            if run.get("state") in {"failed", "timed_out", "interrupted", "unreadable"}:
                result["issues"].append(
                    {
                        "kind": "launch_needs_inspection",
                        "state": run.get("state"),
                        "exit_code": run.get("exit_code"),
                        "run_dir": run["run_dir"],
                    }
                )
            if run.get("pending_tools"):
                result["issues"].append(
                    {
                        "kind": "unfinished_tool_calls",
                        "run_dir": run["run_dir"],
                        "count": run["pending_tools"],
                    }
                )
    result["job_counts"] = dict(Counter(j["state"] for j in result["jobs"]))
    result["endpoint"] = {"checked": False, "ready": None}
    if check_endpoint:
        try:
            wait_endpoint(endpoint, model)
            result["endpoint"] = {"checked": True, "ready": True}
        except (OSError, ValueError, RuntimeError) as error:
            result["endpoint"] = {
                "checked": True,
                "ready": False,
                "error_type": type(error).__name__,
            }
            result["issues"].append({"kind": "endpoint_not_ready"})
    result["recovery"] = (
        "Inspect uncertain tasks and external effects; never replay automatically. Program backups are separate from private history backups."
    )
    return result
