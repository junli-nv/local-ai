"""Install server/client resources in the unpacked project directory."""

import json
import os
from pathlib import Path

from . import __version__, artifacts, images, installlog
from .common import arch, atomic_json, sha256
from .endpoint import endpoint_url
from .paths import client_assets, root, settings
from .profiles import catalog, profile, require_deployable
from .program import source_files


def archive_path(data, policy):
    require_deployable(policy)
    return (
        Path(data)
        / "images"
        / (policy["arch"] + "-" + policy["platform_digest"].split(":")[-1][:16] + ".tar")
    )


def archive_ready(data, policy):
    archive = archive_path(data, policy)
    lock_file = Path(str(archive) + ".lock.json")
    if not archive.is_file() or not lock_file.is_file():
        return False
    lock = json.loads(lock_file.read_text())
    if lock.get("reference") != policy["image"] or lock.get("platform") != policy["platform"]:
        raise ValueError("Local image archive belongs to another recipe")
    if sha256(archive) != lock.get("archive_sha256"):
        raise ValueError("Local image archive checksum mismatch")
    return True


def ensure_archive(data, policy):
    archive = archive_path(data, policy)
    if not archive_ready(data, policy):
        images.export_image(data, policy, archive)
    return archive


def publish_client(directory):
    """Only public binaries/cache live here; histories remain user-private."""
    directory = Path(directory)
    for name in ["bin", "seed-cache"]:
        item = directory / name
        for path in [item, *item.rglob("*")]:
            if path.is_symlink():
                raise ValueError("Public client assets must not contain links")
            if path.is_dir():
                path.chmod(0o755)
            elif path.is_file():
                path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
    (directory / "manifest.json").chmod(0o644)
    directory.chmod(0o755)
    directory.parent.chmod(0o755)


def install(options):
    from .bundle import verify

    if options.role in {"server", "both"}:
        require_deployable(profile(options.profile))
    base = root()
    source_files(base)
    bundle = base / "bundle.json"
    offline = bundle.is_file() if options.offline is None else options.offline
    previous_path = base / "installation.json"
    previous = json.loads(previous_path.read_text()) if previous_path.is_file() else {}
    bundle_sha = sha256(bundle) if bundle.is_file() else None
    if bundle_sha and previous.get("bundle_sha256") != bundle_sha:
        verify(base)
    elif bundle_sha:
        installlog.event(
            "Bundle verified on initial installation; rechecking selected local assets"
        )
    data = Path(options.data_dir).expanduser().resolve()
    endpoint = endpoint_url(options.endpoint) if options.endpoint else None
    catalog_file = os.environ.get("LOCAL_AI_CATALOG")
    if catalog_file:
        selected = Path(catalog_file).expanduser().resolve()
        destination = base / "config/catalog.json"
        destination.parent.mkdir(exist_ok=True)
        if selected != destination:
            atomic_json(destination, json.loads(selected.read_text()), mode=0o644)
    server_result = client_result = None
    model_id = (
        options.model
        or previous.get("model")
        or settings().get("model")
        or catalog()["model"]["served_name"]
    )
    profiles = list(previous.get("profiles", []))
    if options.role in {"server", "both"}:
        policy = profile(options.profile)
        if options.model and options.model != policy["served_name"]:
            raise ValueError("--model must match the selected server profile")
        model_id = policy["served_name"]
        if arch() != policy["arch"]:
            raise ValueError("Selected server profile must match this host CPU architecture")
        model = images.cached_model(data, policy)
        if offline and model is None:
            raise ValueError(
                "Offline installation has no complete model; export the server resources first"
            )
        reference = images.resolve_image(data, policy, allow_missing=True)
        if reference is None:
            if archive_ready(data, policy):
                archive = archive_path(data, policy)
                images.import_image(data, policy, archive, str(archive) + ".lock.json")
            elif offline:
                raise ValueError("Offline installation has no local image or image archive")
            else:
                images.pull(data, policy)
        if model is None:
            model = images.download_model(data, policy)
        archive = ensure_archive(data, policy)
        profiles = sorted(set(profiles + [options.profile]))
        server_result = {"model": model, "image_archive": str(archive), "started": False}
    if options.role in {"client", "both"}:
        assets = client_assets(arch())
        if offline:
            if not (assets / "manifest.json").is_file():
                raise ValueError("Offline bundle has no client for this host CPU architecture")
            local = artifacts.validate(assets)
            if options.client_version and options.client_version != local["version"]:
                raise ValueError("Requested client version is not in this offline bundle")
        (assets / "seed-cache").mkdir(parents=True, exist_ok=True)
        client_result = artifacts.install(assets, version=options.client_version)
        publish_client(assets)
    role = options.role
    if profiles and (client_assets(arch()) / "manifest.json").is_file():
        role = "both"
    record = {
        "format": 1,
        "version": __version__,
        "role": role,
        "profiles": profiles,
        "default_profile": options.profile,
        "model": model_id,
    }
    if endpoint or previous.get("endpoint"):
        record["endpoint"] = endpoint or previous["endpoint"]
    if bundle_sha:
        record["bundle_sha256"] = bundle_sha
    atomic_json(previous_path, record, mode=0o644)
    installlog.event(
        "安装完成（Installed）；program=" + str(base) + "; source=" + str(base / "src")
    )
    if server_result:
        installlog.event(
            "GPU service is not started; next run server start with this host's allocated GPUs"
        )
    return {
        "installed": True,
        "root": str(base),
        "source": str(base / "src"),
        "data_dir": str(data),
        "offline": offline,
        "role": role,
        "server": server_result,
        "client": client_result,
    }
