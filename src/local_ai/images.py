"""Per-platform container provenance and pinned model download."""

import json
import subprocess
from pathlib import Path

from . import installlog
from .common import arch, atomic_json, fingerprint, run, sha256
from .profiles import require_deployable


def inspect_image(reference, platform=None):
    command = ["docker", "image", "inspect"]
    if platform:
        command += ["--platform", platform]
    r = run(command + [reference], check=False)
    if r.returncode == 0:
        return json.loads(r.stdout)[0]
    detail = (r.stderr or "").strip()
    missing = "Error response from daemon: No such image: " + str(reference)
    if detail == missing:
        return None
    raise RuntimeError(
        "Docker image inspection failed (exit=%s): %s"
        % (r.returncode, detail or "No diagnostic output")
    )


def image_identity(image):
    return fingerprint({key: image.get(key) for key in ["Architecture", "Os", "RootFS", "Config"]})


def validate_image(image, policy):
    if image.get("Os") != "linux" or arch(image["Architecture"]) != policy["arch"]:
        raise ValueError("Container image architecture differs from selected server profile")


def lock_path(root, policy):
    return Path(root) / "images" / (policy["arch"] + ".lock.json")


def save_lock(root, policy, image):
    validate_image(image, policy)
    value = {
        "reference": policy["image"],
        "tag": policy["image_tag"],
        "platform": policy["platform"],
        "id": image["Id"],
        "content_identity": image_identity(image),
    }
    atomic_json(lock_path(root, policy), value)
    return value


def resolve_image(root, policy, allow_missing=False):
    require_deployable(policy)
    image = inspect_image(policy["image"], policy["platform"])
    if image:
        validate_image(image, policy)
        return policy["image"]
    path = lock_path(root, policy)
    if not path.is_file():
        if allow_missing:
            return None
        raise RuntimeError("Pinned image absent; run image pull or import its image lock")
    lock = json.loads(path.read_text())
    if lock["reference"] != policy["image"] or lock["platform"] != policy["platform"]:
        raise ValueError("Image lock belongs to a different version/platform")
    found = False
    for ref in [lock["id"], lock["tag"]]:
        image = inspect_image(ref, policy["platform"])
        if image:
            found = True
            validate_image(image, policy)
            if image_identity(image) == lock["content_identity"]:
                return image["Id"]
    if allow_missing and not found:
        return None
    raise RuntimeError("Imported image content does not match its saved lock")


def download_command(command, log):
    if installlog.active():
        return run(command, check=False, timeout=None)
    with Path(log).open("a") as stream:
        return subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)


def pull(root, policy, force=False):
    require_deployable(policy)
    root = Path(root)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    log = installlog.path() or root / "logs" / ("image-pull-" + policy["arch"] + ".log")
    installlog.event(
        "CHECK local image; platform=" + policy["platform"] + "; reference=" + policy["image"]
    )
    image = None
    if not force:
        image = inspect_image(policy["image"], policy["platform"])
        if image is None and lock_path(root, policy).is_file():
            reference = resolve_image(root, policy, allow_missing=True)
            if reference is not None:
                image = inspect_image(reference, policy["platform"])
            else:
                installlog.event("LOCAL IMAGE ABSENT despite saved lock; fetch pinned image")
    if image is not None:
        value = save_lock(root, policy, image)
        installlog.event("REUSE verified local image; no registry access")
        return dict(value, status="already-present", network=False, log=str(log))
    installlog.event("DOWNLOAD image; no reusable local image or --force requested")
    r = download_command(["docker", "pull", "--platform", policy["platform"], policy["image"]], log)
    if r.returncode:
        detail = (getattr(r, "stderr", None) or "").strip()
        raise RuntimeError(
            "Image pull failed (exit=%s); complete output: %s%s"
            % (r.returncode, log, "\nDocker error: " + detail if detail else "")
        )
    image = inspect_image(policy["image"], policy["platform"])
    if image is None:
        raise RuntimeError("Pull completed without a locally inspectable image")
    return dict(save_lock(root, policy, image), status="downloaded", network=True, log=str(log))


def export_image(root, policy, output):
    reference = resolve_image(root, policy)
    image = inspect_image(reference, policy["platform"])
    lock = save_lock(root, policy, image)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    export_tag = (
        "local-ai-export/vllm:"
        + policy["arch"]
        + "-"
        + policy["platform_digest"].split(":")[1][:12]
    )
    lock["tag"] = export_tag
    run(["docker", "image", "tag", reference, export_tag])
    run(
        [
            "docker",
            "image",
            "save",
            "--platform",
            policy["platform"],
            "--output",
            str(output),
            export_tag,
        ],
        timeout=None,
    )
    lock["archive_sha256"] = sha256(output)
    atomic_json(str(output) + ".lock.json", lock)
    return {"image_archive": str(output), "lock": str(output) + ".lock.json"}


def cached_model(root, policy):
    from .server import validate_model

    root = Path(root)
    model = root / "models" / policy["model_directory"]
    if not model.is_dir():
        installlog.event("LOCAL MODEL ABSENT: " + str(model))
        return None
    lockfile = model / "model.lock.json"
    legacy = root / "models/model.lock.json"
    if not lockfile.is_file() and legacy.is_file():
        old = json.loads(legacy.read_text())
        if (
            old.get("repo") == policy["repo"]
            and policy["model_directory"] == policy["repo"].rsplit("/", 1)[-1]
        ):
            lockfile = legacy
    verified = False
    if lockfile.is_file():
        lock = json.loads(lockfile.read_text())
        if lock.get("repo") != policy["repo"] or lock.get("revision") != policy["revision"]:
            raise ValueError(
                "Local model revision conflicts with profile; inspect provenance or explicitly use --force"
            )
        verified = True
    try:
        validate_model(root, policy)
    except ValueError as error:
        if str(error).startswith(
            ("Missing model file:", "Missing weight shard:", "Expected one safetensors index")
        ):
            installlog.event("LOCAL MODEL INCOMPLETE: " + str(error), "WARNING")
            return None
        raise
    if not verified:
        installlog.event(
            "Local model complete; revision lock absent, revision is UNVERIFIED. Reusing files without network.",
            "WARNING",
        )
    installlog.event("REUSE complete local model; repo=" + policy["repo"] + "; network=False")
    return {
        "model": str(model),
        "status": "already-present",
        "network": False,
        "revision_verified": verified,
        "log": str(installlog.path()) if installlog.path() else None,
    }


def download_model(root, policy, force=False):
    require_deployable(policy)
    installlog.event("CHECK local model files and revision; expected=" + policy["revision"])
    if not force:
        cached = cached_model(root, policy)
        if cached is not None:
            return cached
    installlog.event("DOWNLOAD model: missing files or --force requested; repo=" + policy["repo"])

    if arch() != policy["arch"]:
        raise ValueError(
            "Run model download with a native-CPU profile; weights themselves are portable"
        )
    root = Path(root).resolve()
    for name in ["models", "cache", "logs"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    image = resolve_image(root, policy)
    code = (
        "from huggingface_hub import snapshot_download; snapshot_download(repo_id=%r,revision=%r,local_dir=%r,force_download=%r)"
        % (policy["repo"], policy["revision"], "/models/" + policy["model_directory"], force)
    )
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        policy["platform"],
        "--network",
        "host",
        "--mount",
        "type=bind,src=" + str(root / "models") + ",dst=/models",
        "--mount",
        "type=bind,src=" + str(root / "cache") + ",dst=/root/.cache",
        "--entrypoint",
        "python3",
        image,
        "-c",
        code,
    ]
    log = installlog.path() or root / "logs/model-download.log"
    r = download_command(command, log)
    if r.returncode:
        raise RuntimeError("Model download failed; complete output: " + str(log))
    from .server import validate_model

    validate_model(root, policy)
    installlog.event(
        "VERIFY downloaded model: configuration, tokenizer, index and all shard lengths passed"
    )
    atomic_json(
        root / "models" / policy["model_directory"] / "model.lock.json",
        {"repo": policy["repo"], "revision": policy["revision"]},
    )
    return {
        "model": str(root / "models" / policy["model_directory"]),
        "log": str(log),
        "status": "downloaded",
        "network": True,
        "revision_verified": True,
    }


def import_image(root, policy, archive, lock_file):
    require_deployable(policy)
    from .common import sha256

    lock = json.loads(Path(lock_file).read_text())
    if lock["reference"] != policy["image"] or lock["platform"] != policy["platform"]:
        raise ValueError("Archive lock version/platform mismatch")
    if not lock.get("archive_sha256") or sha256(archive) != lock["archive_sha256"]:
        raise ValueError("Image archive checksum mismatch or missing")
    result = run(
        ["docker", "image", "load", "--platform", policy["platform"], "--input", str(archive)],
        timeout=None,
    )
    root = Path(root)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    if not installlog.active():
        (root / "logs" / ("image-import-" + policy["arch"] + ".log")).write_text(
            result.stdout + result.stderr
        )
    for ref in [lock["id"], lock["tag"], policy["image"]]:
        image = inspect_image(ref, policy["platform"])
        if image:
            validate_image(image, policy)
            if image_identity(image) == lock["content_identity"]:
                atomic_json(lock_path(root, policy), lock)
                return {"imported": True, "platform": policy["platform"]}
    raise ValueError("Loaded image content does not match archive lock")
