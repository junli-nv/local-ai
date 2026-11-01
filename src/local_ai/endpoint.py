"""HTTP(S) endpoint validation and model readiness checks."""

import json
import time
import urllib.parse
import urllib.request


def endpoint_url(value):
    if not value or any(c.isspace() for c in value):
        raise ValueError("Endpoint must be a nonempty HTTP(S) base URL without whitespace")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError("Endpoint must be a valid HTTP(S) base URL") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError(
            "Endpoint must be an HTTP(S) base URL without credentials, query or fragment"
        )
    if parsed.hostname in {"0.0.0.0", "::"}:
        raise ValueError(
            "Endpoint must use a reachable server address, not a wildcard listen address"
        )
    return value.rstrip("/")


def wait_endpoint(base, model, seconds=15):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base.rstrip("/") + "/models", timeout=2) as response:
                data = json.load(response)
            if model not in {row["id"] for row in data["data"]}:
                raise ValueError("Server does not advertise model " + model)
            return
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            last = str(error)
        time.sleep(0.2)
    raise RuntimeError("Model API is not ready: " + str(last))
