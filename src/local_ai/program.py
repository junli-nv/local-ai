"""The ordinary unpacked project tree is the installed program."""

from pathlib import Path


def source_files(root):
    root = Path(root)
    if not (root / "local-ai").is_file() or not (root / "src/local_ai/cli.py").is_file():
        raise ValueError("Unpack the complete local-ai program, including local-ai and src/")
    result = {}
    names = [
        "local-ai",
        "install.sh",
        "pyproject.toml",
        "MANIFEST.in",
        ".gitignore",
        "README.md",
        "README.en.md",
        "AGENTS.md",
        "LICENSE",
        "LICENSE.md",
        "src",
        "docs",
        "scripts",
        "tests",
        ".github",
    ]
    for name in names:
        item = root / name
        paths = [item, *item.rglob("*")] if item.is_dir() else [item]
        for path in paths:
            relative = path.relative_to(root)
            if (
                "__pycache__" in relative.parts
                or any(part.endswith(".egg-info") for part in relative.parts)
                or path.name.startswith(".env")
                or path.suffix in {".pyc", ".log"}
            ):
                continue
            if path.is_symlink():
                raise ValueError("Program source must use ordinary files: " + str(path))
            if path.is_file():
                result[str(relative)] = path
    return result
