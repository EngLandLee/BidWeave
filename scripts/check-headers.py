#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Licensed under Apache-2.0; see LICENSE. No warranties.
"""Require per-file SPDX notices; never relabel upstream code or private state."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "target",
    ".runtime",
    ".impeccable",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "coverage",
    "artifacts",
    "backups",
}
CODE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".css",
    ".java",
    ".sql",
    ".mjs",
    ".cjs",
    ".md",
    ".sh",
    ".yaml",
    ".yml",
    ".toml",
    ".html",
    ".xml",
    ".bpmn",
    ".svg",
    ".conf",
    ".properties",
}
CODE_NAMES = {
    "Dockerfile",
    "Makefile",
    ".gitignore",
    ".dockerignore",
    ".env.example",
    "CODEOWNERS",
    ".editorconfig",
    ".gitattributes",
}


def has_notice(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8") as stream:
            first_lines = "".join(line for _, line in zip(range(30), stream))
    except (OSError, UnicodeDecodeError):
        return False
    return (
        "SPDX-FileCopyrightText:" in first_lines
        and "SPDX-License-Identifier:" in first_lines
    )


def source_files(root: Path) -> list[Path]:
    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            check=True,
        )
        paths = [root / name for name in result.stdout.decode().split("\0") if name]
    else:
        paths = list(root.rglob("*"))
    return sorted(
        {
            path
            for path in paths
            if path.is_file()
            and not any(
                part in IGNORED_DIRECTORIES for part in path.relative_to(root).parts
            )
            and path.name not in {"LICENSE", ".DS_Store"}
            and not (path.name.startswith(".env") and path.name != ".env.example")
            and "LICENSES" not in path.relative_to(root).parts
            and not path.name.endswith((".pyc", ".tsbuildinfo"))
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    root = Path(parser.parse_args().root).resolve()
    failures = []
    files = source_files(root)
    for path in files:
        if has_notice(path):
            continue
        sidecar = Path(str(path) + ".license")
        is_code = path.suffix in CODE_SUFFIXES or path.name in CODE_NAMES
        if not is_code and has_notice(sidecar):
            continue
        failures.append(
            f"{path.relative_to(root)}: missing SPDX {'header' if is_code else 'notice or .license sidecar'}"
        )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(
        f"Per-file SPDX notices checked: {len(files)} files (canonical license texts exempt)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
