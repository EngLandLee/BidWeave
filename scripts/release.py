#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
#
# Copyright and license notice: this script may be reused under Apache-2.0.
# It creates source-only release assets and never includes runtime secrets.
"""Create a filtered BidWeave source archive, checksums and inventories."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from datetime import datetime, timezone

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".runtime",
    "runtime",
    "backups",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".impeccable",
    "artifacts",
    ".cache",
}
EXCLUDED_NAMES = {".env", ".env.local", ".env.production", ".DS_Store"}
EXCLUDED_SUFFIXES = {".pyc", ".log"}
VERSION_RE = re.compile(
    r"^v?(0|[1-9][0-9]*)[.](0|[1-9][0-9]*)[.](0|[1-9][0-9]*)(?:[-+][0-9A-Za-z.-]+)?$"
)


def excluded(path: Path, root: Path, output: Path) -> bool:
    relative = path.relative_to(root)
    if path == output or output in path.parents:
        return True
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return True
    if path.name in EXCLUDED_NAMES or (
        path.name.startswith(".env.") and path.name != ".env.example"
    ):
        return True
    return path.suffix in EXCLUDED_SUFFIXES


def source_files(root: Path, output: Path) -> list[Path]:
    files: list[Path] = []
    tracked = (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
        .decode()
        .split("\0")
    )
    for name in filter(None, tracked):
        path = root / name
        if path.is_file() and not excluded(path, root, output):
            if path.is_symlink() and root not in path.resolve().parents:
                raise ValueError(
                    f"Refusing source symlink outside the repository: {name}"
                )
            files.append(path)
    return sorted(files)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dependency_inventory(root: Path) -> dict:
    manifest_names = {
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "uv.lock",
        "compose.yaml",
        "pom.xml",
    }
    unique = [
        path
        for path in source_files(root, root / "dist" / "release")
        if path.name in manifest_names
        or (path.name.startswith("requirements") and path.suffix == ".txt")
    ]
    entries = []
    for path in unique:
        try:
            digest = sha256(path)
        except OSError:
            continue
        entries.append({"path": str(path.relative_to(root)), "sha256": digest})
    return {
        "format": "BidWeave dependency inventory v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "declared_manifests": entries,
        "integrated_boundaries": [
            "Keycloak",
            "Apache APISIX",
            "PostgreSQL",
            "SeaweedFS",
            "Flowable",
            "ClamAV",
            "NATS",
            "Apache Jena/Fuseki",
            "Ollama",
            "n8n (independent license)",
            "TED/eForms/ePO/CCCEV metadata",
            "LLM/model weights (provider-specific license)",
        ],
        "note": "Verify each exact version and upstream license before deployment; no upstream source is vendored.",
    }


def sbom(root: Path, files: list[Path], version: str) -> dict:
    namespace = f"https://github.com/EngLandLee/BidWeave/releases/{version}/sbom"
    packages = [
        {
            "SPDXID": "SPDXRef-Repository",
            "name": "BidWeave source",
            "versionInfo": version,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": True,
            "licenseInfoFromFiles": ["NOASSERTION"],
            "copyrightText": "NOASSERTION",
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "Apache-2.0",
        }
    ]
    sbom_files = []
    file_sha1s = []
    relationships = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Repository",
        }
    ]
    for index, path in enumerate(files, start=1):
        rel = path.relative_to(root).as_posix()
        file_id = f"SPDXRef-File-{index}"
        with path.open("rb") as stream:
            file_sha1 = hashlib.file_digest(stream, "sha1").hexdigest()
        file_sha1s.append(file_sha1)
        sbom_files.append(
            {
                "SPDXID": file_id,
                "fileName": rel,
                "checksums": [
                    {"algorithm": "SHA256", "checksumValue": sha256(path)},
                    {"algorithm": "SHA1", "checksumValue": file_sha1},
                ],
                "licenseConcluded": "NOASSERTION",
                "licenseInfoInFiles": ["NOASSERTION"],
                "copyrightText": "NOASSERTION",
            }
        )
        relationships.append(
            {
                "spdxElementId": "SPDXRef-Repository",
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": file_id,
            }
        )
    packages[0]["packageVerificationCode"] = {
        "packageVerificationCodeValue": hashlib.sha1(
            "".join(sorted(file_sha1s)).encode()
        ).hexdigest()
    }
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"BidWeave-{version}-source",
        "documentNamespace": namespace
        + "/"
        + hashlib.sha256(json.dumps(sbom_files, sort_keys=True).encode()).hexdigest(),
        "creationInfo": {
            "created": datetime.fromtimestamp(
                int(
                    subprocess.check_output(
                        ["git", "log", "-1", "--format=%ct"], cwd=root
                    )
                ),
                timezone.utc,
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "creators": ["Tool: scripts/release.py"],
        },
        "packages": packages,
        "files": sbom_files,
        "relationships": relationships,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", required=True, help="release version, for example 1.0.0"
    )
    parser.add_argument(
        "--workflow-jar", required=True, type=Path, help="built executable workflow JAR"
    )
    parser.add_argument("--output", default="dist/release", help="asset directory")
    args = parser.parse_args()
    version = args.version.lstrip("v")
    if not VERSION_RE.fullmatch(version):
        parser.error(
            "--version must be a simple semantic version (optionally prefixed with v)"
        )
    root = Path(__file__).resolve().parents[1]
    output = (
        (root / args.output).resolve()
        if not Path(args.output).is_absolute()
        else Path(args.output).resolve()
    )
    workflow_jar = (
        args.workflow_jar.resolve()
        if args.workflow_jar.is_absolute()
        else (root / args.workflow_jar).resolve()
    )
    if not workflow_jar.is_file():
        parser.error(f"--workflow-jar must name a regular file: {workflow_jar}")
    output.mkdir(parents=True, exist_ok=True)
    files = source_files(root, output)
    archive = output / f"bidweave-{version}.tar.gz"
    archive_root = f"bidweave-{version}"
    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(
                fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
            ) as tar:
                for path in files:
                    info = tar.gettarinfo(
                        str(path),
                        arcname=f"{archive_root}/{path.relative_to(root).as_posix()}",
                    )
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ""
                    info.pax_headers = {}
                    info.mode = 0o755 if info.mode & 0o111 else 0o644
                    if info.isfile():
                        with path.open("rb") as content:
                            tar.addfile(info, content)
                    else:
                        tar.addfile(info)
    inventory_path = output / "dependency-inventory.json"
    inventory_path.write_text(
        json.dumps(dependency_inventory(root), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    source_sbom_path = output / "sbom.spdx.json"
    source_sbom_path.write_text(
        json.dumps(sbom(root, files, version), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    dependency_sbom_path = output / "dependency-sbom.spdx.json"
    try:
        subprocess.run(
            [
                sys.executable,
                str(root / "scripts/dependency-sbom.py"),
                "--workflow-jar",
                str(workflow_jar),
                "--output",
                str(dependency_sbom_path),
            ],
            cwd=root,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        parser.error(f"dependency SBOM generation failed: {exc}")
    assets = [archive, inventory_path, source_sbom_path, dependency_sbom_path]
    sums = output / "SHA256SUMS"
    sums.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in assets), encoding="utf-8"
    )
    print(f"Created {archive} ({len(files)} source files)")
    print(
        f"Created {sums}, {source_sbom_path.name}, {dependency_sbom_path.name}, {inventory_path.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
