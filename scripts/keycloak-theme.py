#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Purpose: activate the presentation-only BidWeave login theme in a live realm.
"""Select the BidWeave Keycloak login theme without changing realm data.

The script deliberately updates only ``loginTheme`` through the authenticated
Keycloak Admin API. It does not import, reset, recreate, or mutate users,
clients, credentials, or persistent volumes.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / ".env"
DEFAULT_BASE_URL = "http://localhost:8091"
DEFAULT_REALM = "bidweave"
THEME = "bidweave"


class ActivationError(RuntimeError):
    """An explicit, non-secret activation failure."""


class RetryableActivationError(ConnectionError):
    """A transient Keycloak readiness failure."""


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def call_json(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float,
) -> tuple[int, str]:
    request = Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as error:
        # Error bodies are intentionally not printed: they can contain request
        # details, and activation diagnostics only need the status code.
        error.read()
        return error.code, ""
    except (URLError, TimeoutError) as error:
        raise ConnectionError from error


def token(base_url: str, username: str, password: str, timeout: float) -> str:
    payload = urlencode(
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": username,
            "password": password,
        }
    ).encode("ascii")
    status, body = call_json(
        f"{base_url}/realms/master/protocol/openid-connect/token",
        method="POST",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )
    if status in {400, 401, 403}:
        raise ActivationError("Keycloak admin credentials were rejected")
    if status in {500, 502, 503, 504}:
        raise RetryableActivationError
    if status != 200:
        raise ActivationError(f"Keycloak admin token request failed (HTTP {status})")
    try:
        access_token = json.loads(body)["access_token"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ActivationError("Keycloak returned an invalid admin token response") from error
    if not isinstance(access_token, str) or not access_token:
        raise ActivationError("Keycloak returned an empty admin token")
    return access_token


def activate(
    *,
    base_url: str,
    realm: str,
    username: str,
    password: str,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    last_connection_error = False
    while time.monotonic() < deadline:
        try:
            access_token = token(base_url, username, password, min(10.0, timeout))
            headers = {"Authorization": f"Bearer {access_token}"}
            status, body = call_json(
                f"{base_url}/admin/realms/{realm}",
                headers=headers,
                timeout=min(10.0, timeout),
            )
            if status == 401 or status == 403:
                raise ActivationError("Keycloak admin credentials were rejected")
            if status in {500, 502, 503, 504}:
                raise RetryableActivationError
            if status == 404:
                # Realm import can finish shortly after the health endpoint is
                # ready. Keep polling without touching any realm data.
                last_connection_error = False
                time.sleep(1.0)
                continue
            if status != 200:
                raise ActivationError(f"Unable to inspect Keycloak realm (HTTP {status})")
            try:
                current: dict[str, Any] = json.loads(body)
            except json.JSONDecodeError as error:
                raise ActivationError("Keycloak returned invalid realm metadata") from error
            if current.get("loginTheme") != THEME:
                payload = json.dumps({"loginTheme": THEME}).encode("utf-8")
                update_status, _ = call_json(
                    f"{base_url}/admin/realms/{realm}",
                    method="PUT",
                    data=payload,
                    headers={**headers, "Content-Type": "application/json"},
                    timeout=min(10.0, timeout),
                )
                if update_status in {401, 403}:
                    raise ActivationError("Keycloak admin credentials were rejected")
                if update_status in {500, 502, 503, 504}:
                    raise RetryableActivationError
                if not 200 <= update_status < 300:
                    raise ActivationError(
                        f"Unable to activate Keycloak login theme (HTTP {update_status})"
                    )
            print(f"Keycloak login theme active for realm '{realm}'.")
            return
        except ConnectionError:
            last_connection_error = True
            time.sleep(1.0)

    if last_connection_error:
        raise ActivationError("Keycloak was not reachable before the activation timeout")
    raise ActivationError(f"Keycloak realm '{realm}' was not ready before the activation timeout")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--base-url", default=None, help="Keycloak URL (default: localhost:8091)")
    parser.add_argument("--realm", default=None, help="Realm to update (default: bidweave)")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    env = read_env(args.env_file.resolve())
    username = os.environ.get("KEYCLOAK_ADMIN_USERNAME", env.get("KEYCLOAK_ADMIN_USERNAME", "admin"))
    password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", env.get("KEYCLOAK_ADMIN_PASSWORD", ""))
    if not password:
        raise ActivationError("KEYCLOAK_ADMIN_PASSWORD is required; run 'make configure' first")
    base_url = (args.base_url or os.environ.get("KEYCLOAK_URL") or env.get("KEYCLOAK_URL") or DEFAULT_BASE_URL).rstrip("/")
    realm = args.realm or os.environ.get("KEYCLOAK_REALM") or env.get("KEYCLOAK_REALM") or DEFAULT_REALM
    activate(
        base_url=base_url,
        realm=realm,
        username=username,
        password=password,
        timeout=args.timeout,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ActivationError as error:
        raise SystemExit(str(error)) from error
