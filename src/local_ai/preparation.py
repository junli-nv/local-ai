"""Prepare target resources without executing target-platform programs."""

import json
import os
from pathlib import Path

from . import hub, images
from .common import atomic_json
from .deployment import ensure_archive
from .paths import root
from .profiles import profile, require_deployable


def policies(names):
    result = [profile(name) for name in sorted(set(names))]
    identities = {}
    for policy in result:
        require_deployable(policy)
        identity = (policy["repo"], policy["revision"])
        directory = policy["model_directory"]
        if directory in identities and identities[directory] != identity:
            raise ValueError("Selected profiles use conflicting model_directory revisions")
        identities[directory] = identity
    return result


def prepare(options):
    selected = policies(options.profile)
    data = Path(options.data_dir).expanduser().resolve()
    resources = []
    models = {}
    for policy in selected:
        image = images.pull(data, policy, force=options.force)
        key = (policy["repo"], policy["revision"], policy["model_directory"])
        shared = key in models
        if not shared:
            models[key] = hub.download_model(data, policy, force=options.force)
        model = dict(models[key], shared=shared)
        if shared:
            model.update(network=False, status="already-prepared")
        archive = ensure_archive(data, policy)
        resources.append(
            {
                "profile": policy["name"],
                "platform": policy["platform"],
                "model": model,
                "image": image,
                "image_archive": str(archive),
            }
        )
    custom = os.environ.get("LOCAL_AI_CATALOG")
    if custom:
        atomic_json(
            root() / "config/catalog.json", json.loads(Path(custom).read_text()), mode=0o644
        )
    return {"prepared": True, "data_dir": str(data), "resources": resources, "started": False}
