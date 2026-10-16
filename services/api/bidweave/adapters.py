# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed integration adapters; no warranty.
from __future__ import annotations
import json
import boto3
import httpx
import socket
from pathlib import Path
from botocore.config import Config as BotoConfig
from .config import get_settings


class DependencyUnavailable(RuntimeError):
    """A required external service could not complete an operation."""


class ClamAVScanner:
    def scan(self, content: bytes) -> None:
        settings = get_settings()
        try:
            with socket.create_connection(
                (settings.clamav_host, settings.clamav_port), timeout=10
            ) as sock:
                sock.sendall(b"zINSTREAM\0")
                for offset in range(0, len(content), 1024 * 1024):
                    chunk = content[offset : offset + 1024 * 1024]
                    sock.sendall(len(chunk).to_bytes(4, "big") + chunk)
                sock.sendall((0).to_bytes(4, "big"))
                result = sock.recv(4096).decode("utf-8", "replace")
        except Exception as exc:
            raise DependencyUnavailable("malware scanner unavailable") from exc
        if "FOUND" in result:
            raise ValueError("uploaded file rejected by malware scanner")
        if "OK" not in result:
            raise DependencyUnavailable("malware scanner returned no valid result")


class ObjectStore:
    def put(self, key: str, content: bytes, content_type: str) -> None:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError


class S3ObjectStore(ObjectStore):
    def __init__(self):
        settings = get_settings()
        if not settings.s3_access_key or not settings.s3_secret_key:
            raise DependencyUnavailable("object storage credentials are not configured")
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=BotoConfig(signature_version="s3v4"),
        )

    def put(self, key: str, content: bytes, content_type: str) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=key, Body=content, ContentType=content_type
            )
        except Exception as exc:
            raise DependencyUnavailable("object storage upload failed") from exc

    def get(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception as exc:
            raise DependencyUnavailable("object storage download failed") from exc


class LocalObjectStore(ObjectStore):
    def __init__(self):
        self.root = Path(get_settings().local_storage_path).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root not in candidate.parents:
            raise ValueError("unsafe object key")
        return candidate

    def put(self, key: str, content: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as exc:
            raise DependencyUnavailable("object storage download failed") from exc


def object_store() -> ObjectStore:
    return (
        LocalObjectStore()
        if get_settings().storage_backend == "local"
        else S3ObjectStore()
    )


class FlowableClient:
    def __init__(self):
        settings = get_settings()
        self.base = settings.flowable_url.rstrip("/")
        self.auth = (
            (settings.flowable_user, settings.flowable_password)
            if settings.flowable_user
            else None
        )

    def _request(self, method: str, path: str, *, missing_ok: bool = False, **kwargs):
        try:
            response = httpx.request(
                method, self.base + path, auth=self.auth, timeout=10, **kwargs
            )
            if not (missing_ok and response.status_code == 404):
                response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise DependencyUnavailable("workflow service unavailable") from exc

    def start(self, tenant_id: str, case_id: str, revision: int, submitter: str) -> str:
        variables = [
            {"name": n, "type": "integer" if n == "revision" else "string", "value": v}
            for n, v in (
                ("tenant_id", tenant_id),
                ("case_id", case_id),
                ("revision", revision),
                ("submitter", submitter),
            )
        ]
        return str(
            self._request(
                "POST",
                "/runtime/process-instances",
                json={
                    "processDefinitionKey": "bidweave-review",
                    "businessKey": case_id,
                    "variables": variables,
                },
            ).json()["id"]
        )

    def active_for_case(self, case_id: str, revision: int) -> str | None:
        response = self._request(
            "GET",
            "/runtime/process-instances",
            params={"businessKey": case_id, "includeProcessVariables": "true"},
        )
        for item in response.json().get("data", []):
            variables = {
                v.get("name"): v.get("value") for v in item.get("variables", [])
            }
            try:
                matched_revision = int(variables.get("revision", -1))
            except (TypeError, ValueError):
                continue
            if matched_revision == revision:
                return str(item["id"])
        return None

    def tasks(self, process_id: str) -> list[dict]:
        return (
            self._request(
                "GET", "/runtime/tasks", params={"processInstanceId": process_id}
            )
            .json()
            .get("data", [])
        )

    def complete(
        self, task_id: str, decision: str, comment: str, reviewer: str
    ) -> None:
        variables = [
            {"name": name, "type": "string", "value": value}
            for name, value in (
                ("decision", decision),
                ("comment", comment),
                ("reviewer", reviewer),
            )
        ]
        self._request(
            "POST",
            f"/runtime/tasks/{task_id}",
            json={"action": "complete", "variables": variables},
        )

    def completed_review(self, process_id: str) -> dict | None:
        result = self._request(
            "GET",
            "/history/historic-process-instances",
            params={
                "processInstanceId": process_id,
                "includeProcessVariables": "true",
                "size": 1,
            },
        ).json()
        for item in result.get("data", []):
            if (
                item.get("id") == process_id
                and item.get("endTime")
                and not item.get("deleteReason")
            ):
                return {v["name"]: v.get("value") for v in item.get("variables", [])}
        return None

    def delete(self, process_id: str) -> None:
        # Cancellation is complete when the runtime instance is already absent.
        self._request(
            "DELETE", f"/runtime/process-instances/{process_id}", missing_ok=True
        )


class NatsPublisher:
    async def publish(self, subject: str, payload: dict) -> None:
        try:
            import nats

            nc = await nats.connect(get_settings().nats_url, connect_timeout=5)
            try:
                js = nc.jetstream()
                try:
                    await js.add_stream(name="BIDWEAVE", subjects=["bidweave.>"])
                except Exception:
                    # Stream already exists; publish still receives a server acknowledgement.
                    pass
                await js.publish(subject, json.dumps(payload).encode())
            finally:
                await nc.close()
        except Exception as exc:
            raise DependencyUnavailable("event bus unavailable") from exc


def fetch_ted_notice(publication_number: str) -> str:
    settings = get_settings()
    # Restrict caller input to an exact publication number and fixed query shape.
    if not publication_number or any(
        c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789./_-"
        for c in publication_number
    ):
        raise ValueError("invalid publication number")
    escaped = publication_number.replace("\\", "\\\\").replace('"', '\\"')
    query = f'SELECT ?notice ?g WHERE {{ GRAPH ?g {{ ?notice <http://data.europa.eu/a4g/ontology#hasNoticePublicationNumber> "{escaped}" . }} }} LIMIT 1'
    try:
        response = httpx.get(
            settings.ted_endpoint,
            params={"query": query, "format": "application/sparql-results+json"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        bindings = data.get("results", {}).get("bindings", [])
        if not bindings:
            raise ValueError("TED notice not found")
        graph = bindings[0].get("g") or bindings[0]["notice"]
        return str(graph["value"])
    except ValueError:
        raise
    except Exception as exc:
        raise DependencyUnavailable("TED source unavailable") from exc
