"""Per-platform container provenance and pinned model download."""

import json
import subprocess
from pathlib import Path

from .common import arch, atomic_json, fingerprint, run, sha256


def inspect_image(reference, platform=None):
    command = ["docker", "image", "inspect"]
    if platform:
        command += ["--platform", platform]
    r = run(command + [reference], check=False)
    return json.loads(r.stdout)[0] if r.returncode == 0 else None


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


def resolve_image(root, policy):
    image = inspect_image(policy["image"], policy["platform"])
    if image:
        validate_image(image, policy)
        return policy["image"]
    path = lock_path(root, policy)
    if not path.is_file():
        raise RuntimeError("Pinned image absent; run image pull or import its image lock")
    lock = json.loads(path.read_text())
    if lock["reference"] != policy["image"] or lock["platform"] != policy["platform"]:
        raise ValueError("Image lock belongs to a different version/platform")
    for ref in [lock["id"], lock["tag"]]:
        image = inspect_image(ref, policy["platform"])
        if image:
            validate_image(image, policy)
            if image_identity(image) == lock["content_identity"]:
                return image["Id"]
    raise RuntimeError("Imported image content does not match its saved lock")


def pull(root, policy):
    root = Path(root)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    log = root / "logs" / ("image-pull-" + policy["arch"] + ".log")
    with log.open("a") as f:
        r = subprocess.run(
            ["docker", "pull", "--platform", policy["platform"], policy["image"]],
            stdout=f,
            stderr=subprocess.STDOUT,
        )
    if r.returncode:
        raise RuntimeError("Image pull failed; complete output: " + str(log))
    image = inspect_image(policy["image"], policy["platform"])
    if image is None:
        raise RuntimeError("Pull completed without a locally inspectable image")
    return save_lock(root, policy, image)


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


def download_model(root, policy):
    if arch() != policy["arch"]:
        raise ValueError(
            "Run model download with a native-CPU profile; weights themselves are portable"
        )
    root = Path(root).resolve()
    for name in ["models", "cache", "logs"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    image = resolve_image(root, policy)
    code = (
        "from huggingface_hub import snapshot_download; snapshot_download(repo_id=%r,revision=%r,local_dir=%r)"
        % (policy["repo"], policy["revision"], "/models/" + policy["model_directory"])
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
    log = root / "logs/model-download.log"
    with log.open("a") as f:
        r = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        raise RuntimeError("Model download failed; complete output: " + str(log))
    atomic_json(
        root / "models/model.lock.json", {"repo": policy["repo"], "revision": policy["revision"]}
    )
    return {"model": str(root / "models" / policy["model_directory"]), "log": str(log)}


def import_image(root, policy, archive, lock_file):
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
