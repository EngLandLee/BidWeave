#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Licensed under Apache-2.0; see LICENSE. No warranties.
"""Cold, checksummed backups of BidWeave state. Archives contain private secrets."""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--profile", "*"]
# Each path is a dedicated named volume, not a host bind or another project's data.
VOLUMES = {
    "seaweedfs": "/data",
    "keycloak": "/opt/keycloak/data",
    "api": "/data/history",
    "nats": "/data",
    "n8n": "/home/node/.n8n",
    "fuseki": "/fuseki",
}
WRITERS = {
    "api",
    "outbox-worker",
    "mcp",
    "workflow",
    "keycloak",
    "seaweedfs",
    "nats",
    "n8n",
    "fuseki",
}


def run(arguments: list[str], *, stdin=None, stdout=None, sensitive=False) -> str:
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        stdin=stdin,
        stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = (
            "Sensitive operation failed; output withheld."
            if sensitive
            else result.stderr.decode(errors="replace")[-2000:]
        )
        raise RuntimeError(f"{arguments[0]} exited {result.returncode}: {detail}")
    return result.stdout.decode().strip() if stdout is None else ""


def inventory() -> tuple[str, str, list[str], dict[str, str]]:
    postgres = run(COMPOSE + ["ps", "-aq", "postgres"])
    if not postgres:
        raise RuntimeError(
            "Start this project with make up before backing up or restoring."
        )
    metadata = json.loads(run(["docker", "inspect", postgres]))[0]
    project = metadata["Config"]["Labels"]["com.docker.compose.project"]
    running = run(COMPOSE + ["ps", "--services", "--status", "running"]).splitlines()
    if "postgres" not in running:
        raise RuntimeError("PostgreSQL must be running for a logical dump/restore.")
    containers = {}
    for service, mount in VOLUMES.items():
        container = run(COMPOSE + ["ps", "-aq", service])
        if container:
            info = json.loads(run(["docker", "inspect", container]))[0]
            if info["Config"]["Labels"]["com.docker.compose.project"] != project:
                raise RuntimeError("Refusing a container belonging to another project.")
            if not any(
                item["Type"] == "volume" and item["Destination"] == mount
                for item in info["Mounts"]
            ):
                raise RuntimeError(
                    f"{service}: expected dedicated named volume at {mount}"
                )
            containers[service] = container
    if not {"api", "keycloak", "seaweedfs", "nats"} <= containers.keys():
        raise RuntimeError(
            "Core data containers are missing; start the complete core first."
        )
    image = run(COMPOSE + ["images", "-q", "api"]).splitlines()[0]
    return project, image, running, containers


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def backup(directory: Path) -> None:
    project, image, running, containers = inventory()
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    marker = directory / ".partial"
    marker.touch(mode=0o600)
    stopped = sorted(WRITERS.intersection(running))
    try:
        run(COMPOSE + ["stop", "--timeout", "45", *stopped])
        with (directory / "postgres.dump").open("wb") as stream:
            run(
                COMPOSE
                + [
                    "exec",
                    "-T",
                    "postgres",
                    "pg_dump",
                    "-U",
                    "bidweave",
                    "-d",
                    "bidweave",
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                ],
                stdout=stream,
            )
        for service, container in containers.items():
            with (directory / f"{service}.tar.gz").open("wb") as stream:
                run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--network",
                        "none",
                        "--user",
                        "0:0",
                        "--volumes-from",
                        container + ":ro",
                        "--entrypoint",
                        "tar",
                        image,
                        "-C",
                        VOLUMES[service],
                        "--exclude=./import",
                        "-czf",
                        "-",
                        ".",
                    ],
                    stdout=stream,
                )
        shutil.copyfile(ROOT / ".env", directory / ".env")
        files = {
            path.name: {"sha256": digest(path), "bytes": path.stat().st_size}
            for path in directory.iterdir()
            if path.name != ".partial"
        }
        manifest = {
            "format": 1,
            "project": project,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "classification": "private: includes credentials, identity, evidence and workflow data",
            "volumes": {name: VOLUMES[name] for name in containers},
            "files": files,
        }
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        for path in directory.iterdir():
            path.chmod(0o600)
        marker.unlink()
        print(
            f"Complete private backup: {directory}; {len(containers)} data volumes plus PostgreSQL and credentials."
        )
    finally:
        if stopped:
            run(
                COMPOSE
                + ["up", "-d", "--no-recreate", "--wait", "--wait-timeout", "240", *stopped]
            )


def validate_backup(directory: Path) -> dict:
    if (directory / ".partial").exists():
        raise RuntimeError("Incomplete backup: .partial marker exists.")
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("format") != 1 or not isinstance(manifest.get("volumes"), dict):
        raise RuntimeError("Unsupported backup format.")
    volumes = manifest["volumes"]
    if not {"api", "keycloak", "seaweedfs", "nats"} <= volumes.keys():
        raise RuntimeError("Backup omits mandatory core state.")
    if any(VOLUMES.get(name) != mount for name, mount in volumes.items()):
        raise RuntimeError("Backup contains an unexpected volume mapping.")
    expected = {"postgres.dump", ".env"} | {f"{name}.tar.gz" for name in volumes}
    if set(manifest["files"]) != expected:
        raise RuntimeError("Backup file inventory is inconsistent.")
    for name, metadata in manifest["files"].items():
        path = directory / name
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != metadata["bytes"]
            or digest(path) != metadata["sha256"]
        ):
            raise RuntimeError(f"Backup integrity check failed: {name}")
        if name.endswith(".tar.gz"):
            with tarfile.open(path, "r:gz") as archive:
                for member in archive:
                    relative = PurePosixPath(member.name)
                    if (
                        relative.is_absolute()
                        or ".." in relative.parts
                        or not (member.isdir() or member.isfile())
                    ):
                        raise RuntimeError(
                            f"Unsafe archive member in {name}: {member.name}"
                        )
    return manifest


def restore(directory: Path, confirmation: str | None) -> None:
    manifest = validate_backup(directory)
    project, image, running, containers = inventory()
    if confirmation != project:
        raise RuntimeError(
            f"Restore replaces this project's state. Supply --confirm-project {project} explicitly."
        )
    if not manifest["volumes"].keys() <= containers.keys():
        raise RuntimeError(
            "Create the backed-up optional profile containers before restoring."
        )
    stopped = sorted(WRITERS.intersection(running))
    run(COMPOSE + ["stop", "--timeout", "45", *stopped])
    try:
        with (directory / "postgres.dump").open("rb") as stream:
            run(
                COMPOSE
                + [
                    "exec",
                    "-T",
                    "postgres",
                    "pg_restore",
                    "-U",
                    "bidweave",
                    "-d",
                    "bidweave",
                    "--exit-on-error",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--no-privileges",
                ],
                stdin=stream,
            )
        for service, mount in manifest["volumes"].items():
            clear = (
                "from pathlib import Path; import shutil; "
                f"root = Path({mount!r}); "
                "[(shutil.rmtree(path) if path.is_dir() and not path.is_symlink() else path.unlink()) "
                'for path in root.iterdir() if path.name != "import"]'
            )
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--user",
                    "0:0",
                    "--volumes-from",
                    containers[service],
                    "--entrypoint",
                    "python",
                    image,
                    "-c",
                    clear,
                ]
            )
            with (directory / f"{service}.tar.gz").open("rb") as stream:
                run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--network",
                        "none",
                        "--user",
                        "0:0",
                        "-i",
                        "--volumes-from",
                        containers[service],
                        "--entrypoint",
                        "tar",
                        image,
                        "-C",
                        mount,
                        "-xzf",
                        "-",
                    ],
                    stdin=stream,
                )
        shutil.copyfile(directory / ".env", ROOT / ".env")
        (ROOT / ".env").chmod(0o600)
        run([sys.executable, "scripts/configure.py"])
        # Restore to a freshly initialized host as well as the original host.
        values = {}
        for line in (ROOT / ".env").read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"').strip("'")
        password = values["DATABASE_PASSWORD"].replace("'", "''")
        sql = f"SET standard_conforming_strings = on; ALTER ROLE bidweave PASSWORD '{password}';"
        result = subprocess.run(
            COMPOSE
            + [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "bidweave",
                "-d",
                "bidweave",
                "-v",
                "ON_ERROR_STOP=1",
            ],
            cwd=ROOT,
            input=sql.encode(),
            capture_output=True,
        )
        if result.returncode:
            raise RuntimeError(
                "Database credential restoration failed; sensitive output withheld."
            )
        run(
            COMPOSE
            + [
                "up",
                "-d",
                "--force-recreate",
                "--wait",
                "--wait-timeout",
                "240",
                *running,
            ]
        )
        print(
            f"Restored and started {project} from {directory}. Verify SSO, case history and evidence hashes."
        )
    except Exception:
        print(
            "Restore failed. Writer services remain stopped where possible; do not resume against partial state.",
            file=sys.stderr,
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["create", "restore", "verify"])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--confirm-project")
    args = parser.parse_args()
    if args.operation != "create" and args.directory is None:
        parser.error("--directory is required for verify/restore")
    directory = args.directory or ROOT / "backups" / datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")
    directory = directory.resolve()
    if args.operation == "create":
        backup(directory)
    elif args.operation == "restore":
        restore(directory, args.confirm_project)
    else:
        manifest = validate_backup(directory)
        print(
            f"Backup integrity verified: {len(manifest['files'])} private files. Checksums do not prove authenticity."
        )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, tarfile.TarError) as error:
        print(f"Backup operation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
