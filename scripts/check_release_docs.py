"""Check current guide versions and the documentation actually carried by a source archive."""

import argparse
import ast
import json
import re
import tarfile
from pathlib import Path

PINS = re.compile(
    r"https://github\.com/junli-nv/local-ai/archive/refs/tags/(v\d+\.\d+\.\d+)"
    r"|https://raw\.githubusercontent\.com/junli-nv/local-ai/(v\d+\.\d+\.\d+)/"
    r"|--version\s+(v\d+\.\d+\.\d+)"
    r"|local-ai-(v\d+\.\d+\.\d+)-source\.tar\.gz"
    r"|(?:源码下载固定|Source downloads pin)\s+(v\d+\.\d+\.\d+)"
)


def guide_paths(root):
    return sorted(
        [*root.glob("*.md"), *(root / "docs").rglob("*.md"), *(root / "templates").rglob("*.md")]
    )


def check_text(name, text, version):
    if Path(name).name == "validation.md" or re.fullmatch(r"release-[\d.]+\.md", Path(name).name):
        return 0
    count = 0
    for number, line in enumerate(text.splitlines(), 1):
        for match in PINS.finditer(line):
            actual = next(value for value in match.groups() if value)
            if actual != "v" + version:
                raise ValueError(f"{name}:{number}: {actual} != v{version}")
            count += 1
    return count


def check(root, archive=None):
    tree = ast.parse((root / "src/local_ai/__init__.py").read_text())
    version = next(
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)
    )
    if f'version = "{version}"' not in (root / "pyproject.toml").read_text():
        raise ValueError("Python and packaging versions differ")
    files = {str(p.relative_to(root)): p.read_bytes() for p in guide_paths(root)}
    pins = sum(check_text(name, data.decode(), version) for name, data in files.items())
    if archive:
        with tarfile.open(archive) as tar:
            members = {}
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                name = member.name.removeprefix("./")
                if name not in files and "/" in name:
                    name = name.split("/", 1)[1]
                if name in files:
                    members[name] = tar.extractfile(member).read()
            for name, data in files.items():
                if members.get(name) != data:
                    raise ValueError("Missing or stale packaged document: " + name)
    return {
        "version": version,
        "documents": len(files),
        "current_version_references": pins,
        "archive_verified": archive is not None,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.root, args.archive)))
