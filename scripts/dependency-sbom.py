#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
#
# Copyright and license notice: this script may be reused under Apache-2.0.
"""Generate a deterministic SPDX 2.3 dependency inventory from checked-in locks and a workflow JAR.

The parser is deliberately offline: it only consumes repository lockfiles, compose.yaml, and
an executable Spring Boot JAR supplied by --workflow-jar.  Missing or malformed inputs are
errors; unknown upstream license metadata is represented as NOASSERTION.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Any
import xml.etree.ElementTree as ET
import zipfile


class SBOMError(ValueError):
    """An input did not satisfy the lock or artifact contract."""


NOASSERTION = "NOASSERTION"
_FIXED_CREATED = "1970-01-01T00:00:00Z"


# Only map names whose spelling is unambiguous.  All other upstream metadata remains a
# comment and NOASSERTION rather than becoming an invented SPDX expression.
_LICENSE_NAMES = {
    "Apache License, Version 2.0": "Apache-2.0",
    "The Apache Software License, Version 2.0": "Apache-2.0",
    "MIT License": "MIT",
    "BSD 2-Clause License": "BSD-2-Clause",
    "BSD 3-Clause License": "BSD-3-Clause",
    "Eclipse Public License - v 1.0": "EPL-1.0",
    "Eclipse Public License v1.0": "EPL-1.0",
    "Eclipse Public License 1.0": "EPL-1.0",
    "Mozilla Public License Version 2.0": "MPL-2.0",
    "GNU Lesser General Public License v2.1": "LGPL-2.1-only",
    "GNU Lesser General Public License, version 2.1": "LGPL-2.1-only",
}
_LICENSE_IDS = {
    "Apache-2.0",
    "MIT",
    "ISC",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "EPL-1.0",
    "EPL-2.0",
    "MPL-2.0",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "Python-2.0",
    "PSF-2.0",
    "CC0-1.0",
    "Unlicense",
    "Zlib",
    "Unicode-DFS-2016",
    "WTFPL",
    "0BSD",
    "NOASSERTION",
    "NONE",
}


def fail(message: str) -> SBOMError:
    return SBOMError(message)


def require_file(path: Path, label: str) -> bytes:
    if not path.is_file():
        raise fail(f"{label} is missing or not a regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise fail(f"cannot read {label}: {path}: {exc}") from exc


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checksum(algorithm: str, value: str) -> dict[str, str]:
    return {"algorithm": algorithm, "checksumValue": value.lower()}


def purl(kind: str, name: str, version: str) -> str:
    # The names used by these ecosystems are deliberately restricted below, so no network
    # lookup or registry normalization is needed here.
    from urllib.parse import quote

    if kind == "maven":
        if ":" not in name:
            raise fail(f"Maven purl requires group:artifact coordinates: {name!r}")
        group, artifact = name.split(":", 1)
        encoded = f"{quote(group, safe='-._~')}/{quote(artifact, safe='-._~')}"
    elif kind == "npm":
        encoded = quote(name, safe="/")
    else:
        encoded = quote(name, safe="-._~")
    return f"pkg:{kind}/{encoded}@{version}"


def external_purl(locator: str) -> list[dict[str, str]]:
    return [
        {
            "referenceCategory": "PACKAGE-MANAGER",
            "referenceType": "purl",
            "referenceLocator": locator,
        }
    ]


def package_id(ecosystem: str, name: str, version: str, discriminator: str = "") -> str:
    token = f"{ecosystem}\x00{name}\x00{version}\x00{discriminator}".encode()
    return f"SPDXRef-{ecosystem}-{hashlib.sha256(token).hexdigest()[:24]}"


def lock_file(relative: str, digest: str, comment: str) -> dict[str, Any]:
    return {
        "SPDXID": package_id("File", relative, digest),
        "fileName": relative,
        "checksums": [checksum("SHA256", digest)],
        "licenseConcluded": NOASSERTION,
        "licenseInfoInFiles": [NOASSERTION],
        "copyrightText": NOASSERTION,
        "comment": comment,
    }


def package_base(
    spdx_id: str,
    name: str,
    version: str,
    download: str = NOASSERTION,
    *,
    comment: str | None = None,
) -> dict[str, Any]:
    package: dict[str, Any] = {
        "SPDXID": spdx_id,
        "name": name,
        "versionInfo": version,
        "downloadLocation": download,
        "filesAnalyzed": False,
        "licenseConcluded": NOASSERTION,
        "licenseDeclared": NOASSERTION,
    }
    if comment:
        package["comment"] = comment
    return package


def license_expression(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value in _LICENSE_IDS:
        return value
    if value in _LICENSE_NAMES:
        return _LICENSE_NAMES[value]
    # npm occasionally records a simple SPDX AND/OR expression.  Accept it only when each
    # atom is an SPDX identifier from the conservative set above.
    atoms = re.split(r"\s+(?:AND|OR)\s+", value)
    operators = re.findall(r"\s+(AND|OR)\s+", value)
    if (
        atoms
        and len(atoms) == len(operators) + 1
        and all(atom in _LICENSE_IDS for atom in atoms)
    ):
        rendered = atoms[0]
        for operator, atom in zip(operators, atoms[1:]):
            rendered += f" {operator} {atom}"
        return rendered
    return None


def parse_uv_lock(raw: bytes) -> list[dict[str, Any]]:
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise fail(f"malformed uv.lock: {exc}") from exc
    if data.get("version") != 1 or not isinstance(data.get("package"), list):
        raise fail("uv.lock must contain version = 1 and [[package]] entries")
    packages: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in data["package"]:
        if not isinstance(entry, dict):
            raise fail("uv.lock contains a non-object package entry")
        name, version = entry.get("name"), entry.get("version")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(version, str)
            or not version
        ):
            raise fail("uv.lock package lacks a non-empty name or version")
        source = entry.get("source")
        if not isinstance(source, dict):
            raise fail(f"uv.lock package {name} has no source table")
        # The editable project itself is represented by the project package, not as a third
        # party component.  An editable dependency with another source is still malformed for
        # this inventory rather than silently guessed.
        if "editable" in source:
            continue
        if "registry" not in source or not isinstance(source["registry"], str):
            raise fail(f"uv.lock package {name} has unsupported source metadata")
        key = (name, version)
        if key in seen:
            raise fail(f"uv.lock contains duplicate package {name}=={version}")
        seen.add(key)
        hashes: set[str] = set()
        urls: list[str] = []
        for artifact_key in ("sdist", "wheels"):
            artifacts = entry.get(artifact_key, [])
            if artifact_key == "sdist" and isinstance(artifacts, dict):
                artifacts = [artifacts]
            if not isinstance(artifacts, list):
                raise fail(f"uv.lock package {name} has malformed {artifact_key}")
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    raise fail(f"uv.lock package {name} has a malformed artifact")
                artifact_hash = artifact.get("hash")
                if not isinstance(artifact_hash, str) or not re.fullmatch(
                    r"sha256:[0-9a-f]{64}", artifact_hash
                ):
                    raise fail(f"uv.lock package {name} has a malformed artifact hash")
                hashes.add(artifact_hash[7:])
                if isinstance(artifact.get("url"), str):
                    urls.append(artifact["url"])
        component_id = package_id("PyPI", name, version)
        component = package_base(
            component_id, name, version, min(urls) if urls else NOASSERTION
        )
        if hashes:
            component["checksums"] = [
                checksum("SHA256", item) for item in sorted(hashes)
            ]
        component["externalRefs"] = external_purl(
            purl("pypi", name.lower().replace("_", "-"), version)
        )
        component["comment"] = json.dumps(
            {
                "provenance": "services/api/uv.lock",
                "registry": source["registry"],
                "hashes_present": bool(hashes),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        packages.append(component)
    if not packages:
        raise fail("uv.lock contains no registry packages")
    return packages


def parse_requirements(raw: bytes) -> list[dict[str, Any]]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise fail(f"malformed MCP requirements lock: {exc}") from exc
    packages: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    current: dict[str, Any] | None = None
    requirement_re = re.compile(
        r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[[^\]]+\])?==([^\\\s]+)\s*(\\)?$"
    )
    hash_re = re.compile(r"^\s+--hash=(sha256:[0-9a-f]{64})\s*(?:\\)?$")
    for line_number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = requirement_re.fullmatch(line)
        if match:
            if current is not None:
                packages.append(current)
            name, version, continuation = match.group(1), match.group(2), match.group(3)
            current = {"name": name, "version": version, "hashes": set()}
            if continuation is None:
                # A lock line without a continuation is valid only if no hashes follow.  This
                # project requires hash locking, so defer the useful error to finalization.
                pass
            continue
        hash_match = hash_re.fullmatch(line)
        if hash_match and current is not None:
            current["hashes"].add(hash_match.group(1)[7:])
            continue
        raise fail(f"malformed MCP requirements lock at line {line_number}: {line!r}")
    if current is not None:
        packages.append(current)
    if not packages:
        raise fail("MCP requirements lock contains no requirements")
    result: list[dict[str, Any]] = []
    for item in packages:
        name, version, hashes = item["name"], item["version"], item["hashes"]
        key = (name, version)
        if key in seen:
            raise fail(
                f"MCP requirements lock contains duplicate package {name}=={version}"
            )
        seen.add(key)
        if not hashes:
            raise fail(
                f"MCP requirements package {name}=={version} has no sha256 hashes"
            )
        component = package_base(package_id("MCP", name, version), name, version)
        component["checksums"] = [
            checksum("SHA256", item_hash) for item_hash in sorted(hashes)
        ]
        component["externalRefs"] = external_purl(
            purl("pypi", name.lower().replace("_", "-"), version)
        )
        component["comment"] = json.dumps(
            {"provenance": "services/mcp/requirements.txt", "hashes_present": True},
            sort_keys=True,
            separators=(",", ":"),
        )
        result.append(component)
    return result


def npm_name(key: str) -> str:
    if not key.startswith("node_modules/"):
        raise fail(f"unsupported package-lock package key: {key!r}")
    parts = key.split("/")
    marker = max(i for i, part in enumerate(parts) if part == "node_modules")
    rest = parts[marker + 1 :]
    if not rest or (rest[0].startswith("@") and len(rest) < 2):
        raise fail(f"malformed package-lock package key: {key!r}")
    return "/".join(rest[:2] if rest[0].startswith("@") else rest[:1])


def parse_npm_lock(raw: bytes) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise fail(f"malformed package-lock.json: {exc}") from exc
    if (
        not isinstance(data, dict)
        or data.get("lockfileVersion") != 3
        or not isinstance(data.get("packages"), dict)
    ):
        raise fail("package-lock.json must be lockfileVersion 3 with a packages object")
    root_package = data["packages"].get("")
    if not isinstance(root_package, dict) or not isinstance(
        root_package.get("name"), str
    ):
        raise fail("package-lock.json lacks a valid root package entry")
    result: list[dict[str, Any]] = []
    for key in sorted(data["packages"]):
        if key == "":
            continue
        info = data["packages"][key]
        if not isinstance(info, dict) or info.get("link") is True:
            continue
        name = npm_name(key)
        version = info.get("version")
        if not isinstance(version, str) or not version:
            raise fail(f"package-lock entry {key!r} lacks a version")
        resolved = info.get("resolved", NOASSERTION)
        if not isinstance(resolved, str):
            raise fail(f"package-lock entry {key!r} has malformed resolved URL")
        component = package_base(
            package_id("NPM", name, version, key), name, version, resolved
        )
        integrity = info.get("integrity")
        if integrity is not None:
            if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
                raise fail(f"package-lock entry {key!r} has unsupported integrity")
            try:
                encoded = base64.b64decode(integrity[7:], validate=True)
            except (ValueError, binascii.Error) as exc:
                raise fail(
                    f"package-lock entry {key!r} has malformed integrity"
                ) from exc
            if len(encoded) != 64:
                raise fail(
                    f"package-lock entry {key!r} has a non-SHA512 integrity value"
                )
            component["checksums"] = [checksum("SHA512", encoded.hex())]
        declared = license_expression(info.get("license"))
        if declared:
            component["licenseDeclared"] = declared
        elif info.get("license") is not None:
            component["licenseComments"] = (
                f"Unmapped package-lock license metadata: {info['license']!r}"
            )
        component["externalRefs"] = external_purl(purl("npm", name, version))
        component["comment"] = json.dumps(
            {
                "provenance": "apps/web/package-lock.json",
                "lock_path": key,
                "integrity_present": integrity is not None,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        result.append(component)
    if not result:
        raise fail("package-lock.json contains no installed packages")
    return result


@dataclass(frozen=True)
class MavenMetadata:
    group: str | None
    artifact: str | None
    version: str | None
    licenses: tuple[dict[str, str], ...]
    pom_path: str | None
    license_files: tuple[str, ...]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def java_properties(raw: bytes, source: str) -> dict[str, str]:
    try:
        text = raw.decode("iso-8859-1")
    except UnicodeDecodeError as exc:
        raise fail(f"malformed {source}: {exc}") from exc
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        match = re.split(r"(?<!\\)[:=\s]", line, maxsplit=1)
        if len(match) != 2 or not match[0].strip():
            raise fail(f"malformed {source} property line: {line!r}")
        result[match[0].strip()] = (
            match[1].strip().replace(r"\:", ":").replace(r"\=", "=")
        )
    return result


def maven_metadata(
    zf: zipfile.ZipFile, pom_directory: str | None = None
) -> MavenMetadata:
    names = sorted(set(zf.namelist()))
    pom_properties = [
        name
        for name in names
        if re.fullmatch(r"META-INF/maven/[^/]+/[^/]+/pom.properties", name)
        and (pom_directory is None or name.startswith(pom_directory + "/"))
    ]
    pom_xmls = [
        name
        for name in names
        if re.fullmatch(r"META-INF/maven/[^/]+/[^/]+/pom.xml", name)
        and (pom_directory is None or name.startswith(pom_directory + "/"))
    ]
    group: str | None = None
    artifact: str | None = None
    version: str | None = None
    pom_path: str | None = None
    licenses: list[dict[str, str]] = []
    if len(pom_properties) > 1:
        raise fail("nested Maven JAR contains multiple pom.properties files")
    if pom_properties:
        pom_path = pom_properties[0]
        props = java_properties(zf.read(pom_path), pom_path)
        group, artifact, version = (
            props.get("groupId"),
            props.get("artifactId"),
            props.get("version"),
        )
    if len(pom_xmls) > 1:
        raise fail("nested Maven JAR contains multiple pom.xml files")
    if pom_xmls:
        pom_path = pom_path or pom_xmls[0]
        try:
            root = ET.fromstring(zf.read(pom_xmls[0]))
        except (ET.ParseError, UnicodeDecodeError) as exc:
            raise fail(f"malformed embedded Maven POM {pom_xmls[0]}: {exc}") from exc
        values: dict[str, str] = {}
        for child in root:
            tag = local_name(child.tag)
            if (
                tag in {"groupId", "artifactId", "version"}
                and child.text
                and child.text.strip()
            ):
                values[tag] = child.text.strip()
        group = group or values.get("groupId")
        artifact = artifact or values.get("artifactId")
        version = version or values.get("version")
        for license_node in root.iter():
            if local_name(license_node.tag) != "license":
                continue
            item: dict[str, str] = {}
            for child in license_node:
                child_name = local_name(child.tag)
                if (
                    child.text
                    and child.text.strip()
                    and child_name in {"name", "url", "distribution"}
                ):
                    item[child_name] = child.text.strip()
            if item:
                licenses.append(item)
    if any(
        value is not None and (not value or value.startswith("${"))
        for value in (group, artifact, version)
    ):
        group = artifact = version = None
    license_files = tuple(
        name
        for name in names
        if name.upper().split("/")[-1].startswith(("LICENSE", "LICENCE", "NOTICE"))
    )
    return MavenMetadata(
        group, artifact, version, tuple(licenses), pom_path, license_files
    )


def workflow_maven_metadata(raw: bytes) -> MavenMetadata:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as outer:
            return maven_metadata(outer)
    except zipfile.BadZipFile as exc:
        raise fail(f"workflow JAR is not a valid ZIP/JAR: {exc}") from exc


def parse_workflow_jar(raw: bytes) -> list[dict[str, Any]]:
    try:
        outer = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise fail(f"workflow JAR is not a valid ZIP/JAR: {exc}") from exc
    with outer:
        names = outer.namelist()
        if len(names) != len(set(names)):
            raise fail("workflow JAR contains duplicate ZIP member names")
        if outer.testzip() is not None:
            raise fail("workflow JAR contains a corrupt ZIP member")
        lib_names = sorted(
            name
            for name in names
            if name.startswith("BOOT-INF/lib/") and name.endswith(".jar")
        )
        if not lib_names:
            raise fail(
                "workflow JAR does not contain BOOT-INF/lib/*.jar Spring Boot dependencies"
            )
        packages: list[dict[str, Any]] = []
        for lib_name in lib_names:
            nested_raw = outer.read(lib_name)
            try:
                nested = zipfile.ZipFile(io.BytesIO(nested_raw))
            except zipfile.BadZipFile as exc:
                raise fail(
                    f"embedded dependency {lib_name} is not a valid JAR: {exc}"
                ) from exc
            with nested:
                nested_names = nested.namelist()
                if len(nested_names) != len(set(nested_names)):
                    raise fail(
                        f"embedded dependency {lib_name} contains duplicate ZIP names"
                    )
                if nested.testzip() is not None:
                    raise fail(
                        f"embedded dependency {lib_name} contains a corrupt ZIP member"
                    )
                directories = sorted(
                    {
                        name.rsplit("/", 1)[0]
                        for name in nested_names
                        if re.fullmatch(
                            r"META-INF/maven/[^/]+/[^/]+/pom\.(properties|xml)", name
                        )
                    }
                )
                records = [
                    maven_metadata(nested, directory) for directory in directories
                ]
                if not records:
                    records = [maven_metadata(nested)]
            primary = next(
                (
                    item
                    for item in records
                    if Path(lib_name).name == f"{item.artifact}-{item.version}.jar"
                ),
                records[0] if len(records) == 1 else None,
            )
            if primary is None:
                primary = MavenMetadata(
                    None, None, None, (), None, records[0].license_files
                )
                records.insert(0, primary)
            for metadata in records:
                is_primary = metadata is primary
                name = metadata.artifact or Path(lib_name).stem
                version = metadata.version or NOASSERTION
                coordinate = f"{metadata.group}:{name}" if metadata.group else None
                location = (
                    lib_name if is_primary else f"{lib_name}!/{metadata.pom_path}"
                )
                component = package_base(
                    package_id("Maven", coordinate or name, version, location),
                    coordinate or name,
                    version,
                    comment=None,
                )
                # The enclosing JAR checksum is not a checksum of a shaded component.
                if is_primary:
                    component["checksums"] = [
                        checksum("SHA256", digest_bytes(nested_raw))
                    ]
                if coordinate and metadata.version:
                    component["externalRefs"] = external_purl(
                        purl("maven", coordinate, metadata.version)
                    )
                mapped = {
                    license_expression(item.get("name")) for item in metadata.licenses
                }
                if len(mapped) == 1 and None not in mapped:
                    component["licenseDeclared"] = next(iter(mapped))
                comment_data: dict[str, Any] = {
                    "provenance": "workflow JAR BOOT-INF/lib"
                    if is_primary
                    else "embedded/shaded Maven metadata",
                    "embedded_path": lib_name,
                    "pom_path": metadata.pom_path,
                    "pom_licenses": [dict(item) for item in metadata.licenses],
                    "license_files": list(metadata.license_files),
                    "license_metadata_limitations": (
                        "Embedded metadata identifies a component but not its complete class contents. "
                        "License text is not interpreted; multiple POM licenses do not establish AND/OR semantics."
                    ),
                }
                component["comment"] = json.dumps(
                    comment_data, sort_keys=True, separators=(",", ":")
                )
                packages.append(component)
    return packages


def parse_compose_images(raw: bytes) -> list[dict[str, Any]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise fail(f"malformed compose.yaml: {exc}") from exc
    images: list[dict[str, Any]] = []
    if not re.search(r"(?m)^services:\s*$", text):
        raise fail("compose.yaml lacks a services mapping")
    image_line = re.compile(r"^\s{2,}image:\s*(\S+)\s*$")
    for line_number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if "image:" not in line:
            continue
        match = image_line.fullmatch(line)
        if not match:
            raise fail(
                f"unsupported or malformed compose image declaration at line {line_number}"
            )
        reference = match.group(1)
        if "${" in reference or any(char in reference for char in "'\"[]{}"):
            raise fail(
                f"unresolved or malformed compose image reference at line {line_number}"
            )
        digest = None
        if "@" in reference:
            base, digest = reference.rsplit("@", 1)
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise fail(f"malformed compose image digest at line {line_number}")
        else:
            base = reference
        tag = None
        last_slash = base.rfind("/")
        last_colon = base.rfind(":")
        if last_colon > last_slash:
            base, tag = base[:last_colon], base[last_colon + 1 :]
            if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag):
                raise fail(f"malformed compose image tag at line {line_number}")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", base):
            raise fail(f"malformed compose image name at line {line_number}")
        if not base:
            raise fail(f"malformed compose image name at line {line_number}")
        images.append(
            {
                "reference": reference,
                "name": base,
                "tag": tag,
                "digest": digest,
                "line": line_number,
            }
        )
    return images


def build_document(root: Path, workflow_jar: Path) -> dict[str, Any]:
    paths = {
        "uv_lock": root / "services/api/uv.lock",
        "mcp_requirements": root / "services/mcp/requirements.txt",
        "npm_lock": root / "apps/web/package-lock.json",
        "compose": root / "compose.yaml",
    }
    raw_inputs = {key: require_file(path, key) for key, path in paths.items()}
    jar_raw = require_file(workflow_jar, "workflow JAR")
    py_packages = parse_uv_lock(raw_inputs["uv_lock"])
    mcp_packages = parse_requirements(raw_inputs["mcp_requirements"])
    npm_packages = parse_npm_lock(raw_inputs["npm_lock"])
    workflow_metadata = workflow_maven_metadata(jar_raw)
    maven_packages = parse_workflow_jar(jar_raw)
    images = parse_compose_images(raw_inputs["compose"])

    provenance = {
        "services/api/uv.lock": digest_bytes(raw_inputs["uv_lock"]),
        "services/mcp/requirements.txt": digest_bytes(raw_inputs["mcp_requirements"]),
        "apps/web/package-lock.json": digest_bytes(raw_inputs["npm_lock"]),
        "compose.yaml": digest_bytes(raw_inputs["compose"]),
        "workflow_jar_sha256": digest_bytes(jar_raw),
    }
    namespace_hash = digest_bytes(
        "".join(
            f"{key}={value}\n" for key, value in sorted(provenance.items())
        ).encode()
    )
    project_id = "SPDXRef-Project"
    project_version = workflow_metadata.version or NOASSERTION
    project = package_base(
        project_id,
        "BidWeave",
        project_version,
        comment="Project root for dependency relationships.",
    )
    project["licenseDeclared"] = "Apache-2.0"

    files = [
        lock_file(
            "services/api/uv.lock",
            provenance["services/api/uv.lock"],
            "Checked-in Python lock provenance.",
        ),
        lock_file(
            "services/mcp/requirements.txt",
            provenance["services/mcp/requirements.txt"],
            "Checked-in hash-locked MCP Python requirements provenance.",
        ),
        lock_file(
            "apps/web/package-lock.json",
            provenance["apps/web/package-lock.json"],
            "Checked-in npm lock provenance.",
        ),
        lock_file(
            "compose.yaml",
            provenance["compose.yaml"],
            "Declared container image source; tags are not treated as digests.",
        ),
        {
            "SPDXID": "SPDXRef-WorkflowJarFile",
            "fileName": "workflow-artifact.jar",
            "checksums": [checksum("SHA256", provenance["workflow_jar_sha256"])],
            "licenseConcluded": NOASSERTION,
            "licenseInfoInFiles": [NOASSERTION],
            "copyrightText": NOASSERTION,
            "comment": "Runtime-supplied executable JAR; path intentionally omitted from the artifact.",
        },
    ]
    file_sha1s = {
        path.relative_to(root).as_posix(): hashlib.sha1(raw_inputs[key]).hexdigest()
        for key, path in paths.items()
    }
    file_sha1s["workflow-artifact.jar"] = hashlib.sha1(jar_raw).hexdigest()
    for file_entry in files:
        file_entry["checksums"].append(
            checksum("SHA1", file_sha1s[file_entry["fileName"]])
        )
    packages = [project]
    packages.extend(py_packages)
    packages.extend(mcp_packages)
    packages.extend(npm_packages)
    packages.extend(maven_packages)
    workflow_name = "BidWeave Workflow executable JAR"
    workflow_version = NOASSERTION
    workflow_coordinate = None
    if (
        workflow_metadata.group
        and workflow_metadata.artifact
        and workflow_metadata.version
    ):
        workflow_coordinate = f"{workflow_metadata.group}:{workflow_metadata.artifact}"
        workflow_name = workflow_coordinate
        workflow_version = workflow_metadata.version
    workflow_comment = {
        "provenance": "workflow executable JAR",
        "pom_path": workflow_metadata.pom_path,
        "pom_licenses": list(workflow_metadata.licenses),
        "license_files": list(workflow_metadata.license_files),
        "license_metadata_limitations": "Embedded license text is not interpreted; unknown names remain NOASSERTION.",
    }
    workflow_package = package_base(
        "SPDXRef-WorkflowJar",
        workflow_name,
        workflow_version,
        comment=json.dumps(workflow_comment, sort_keys=True, separators=(",", ":")),
    )
    workflow_package["checksums"] = [
        checksum("SHA256", provenance["workflow_jar_sha256"])
    ]
    workflow_mapped = {
        license_expression(item.get("name")) for item in workflow_metadata.licenses
    }
    if len(workflow_mapped) == 1 and None not in workflow_mapped:
        workflow_package["licenseDeclared"] = next(iter(workflow_mapped))
    if workflow_coordinate and workflow_metadata.version:
        workflow_package["externalRefs"] = external_purl(
            purl("maven", workflow_coordinate, workflow_metadata.version)
        )
    packages.append(workflow_package)
    for owner, contained_files in ((project, files), (workflow_package, [files[-1]])):
        owner["filesAnalyzed"] = True
        owner["licenseInfoFromFiles"] = [NOASSERTION]
        owner["copyrightText"] = NOASSERTION
        owner["packageVerificationCode"] = {
            "packageVerificationCodeValue": hashlib.sha1(
                "".join(
                    sorted(file_sha1s[item["fileName"]] for item in contained_files)
                ).encode()
            ).hexdigest()
        }
    for image in images:
        image_ref = image["digest"] or image["tag"]
        version = image_ref or NOASSERTION
        package = package_base(
            package_id("Container", image["name"], version, image["reference"]),
            image["name"],
            version,
            comment=json.dumps(
                {
                    "provenance": "compose.yaml",
                    "reference": image["reference"],
                    "digest_pinned": image["digest"] is not None,
                    "line": image["line"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        if image["digest"]:
            package["externalRefs"] = external_purl(
                f"pkg:docker/{image['name']}@{image['digest']}"
            )
        elif image["tag"]:
            package["externalRefs"] = external_purl(
                f"pkg:docker/{image['name']}@{image['tag']}"
            )
        packages.append(package)

    relationships: list[dict[str, str]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": project_id,
        }
    ]
    for file_entry in files:
        relationships.append(
            {
                "spdxElementId": project_id,
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": file_entry["SPDXID"],
            }
        )
    relationships.append(
        {
            "spdxElementId": "SPDXRef-WorkflowJar",
            "relationshipType": "CONTAINS",
            "relatedSpdxElement": "SPDXRef-WorkflowJarFile",
        }
    )
    for package in packages:
        if package["SPDXID"] != project_id:
            relationships.append(
                {
                    "spdxElementId": project_id,
                    "relationshipType": "DEPENDS_ON",
                    "relatedSpdxElement": package["SPDXID"],
                }
            )
    relationships = sorted(
        relationships,
        key=lambda item: (
            item["spdxElementId"],
            item["relationshipType"],
            item["relatedSpdxElement"],
        ),
    )
    doc_comment = {
        "schema": "BidWeave dependency SBOM input inventory v1",
        "tool": "scripts/dependency-sbom.py",
        "deterministic": True,
        "provenance_sha256": provenance,
        "limitations": [
            "No registry or network metadata is fetched; package licenses are only those present in lockfiles or embedded Maven metadata.",
            "Unknown or non-SPDX upstream license names and embedded license text are reported as NOASSERTION.",
            "Compose image tags are declarations, not content digests; only explicit @sha256 references are digest-pinned.",
            "Python uv.lock and requirements.txt are inventories of locked metadata, not proof of host installation.",
        ],
    }
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "BidWeave dependency inventory",
        "documentNamespace": f"https://bidweave.invalid/spdx/{namespace_hash}",
        "creationInfo": {
            "created": _FIXED_CREATED,
            "creators": ["Tool: scripts/dependency-sbom.py"],
        },
        "documentComment": json.dumps(
            doc_comment, sort_keys=True, separators=(",", ":")
        ),
        "packages": packages,
        "files": files,
        "relationships": relationships,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    output_group = parser.add_mutually_exclusive_group(required=True)
    output_group.add_argument(
        "--output",
        type=Path,
        help="SPDX JSON file, or artifact directory (writes dependency-sbom.spdx.json)",
    )
    output_group.add_argument(
        "--output-dir",
        type=Path,
        help="artifact directory (writes dependency-sbom.spdx.json)",
    )
    parser.add_argument(
        "--workflow-jar",
        required=True,
        type=Path,
        help="actual executable Spring Boot JAR, usually copied from /opt/bidweave/app.jar",
    )
    parser.add_argument(
        "--root", type=Path, help="repository root (defaults to the parent of scripts/)"
    )
    args = parser.parse_args(argv)
    root = args.root.resolve() if args.root else Path(__file__).resolve().parents[1]
    output = (
        args.output
        if args.output is not None
        else args.output_dir / "dependency-sbom.spdx.json"
    ).resolve()
    if output.exists() and output.is_dir():
        output = output / "dependency-sbom.spdx.json"
    elif output.suffix.lower() != ".json":
        output.mkdir(parents=True, exist_ok=True)
        output = output / "dependency-sbom.spdx.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        document = build_document(root, args.workflow_jar.resolve())
        output.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (
        OSError,
        SBOMError,
        zipfile.LargeZipFile,
        RuntimeError,
        NotImplementedError,
    ) as exc:
        print(f"dependency-sbom: error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote deterministic SPDX 2.3 dependency inventory: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
