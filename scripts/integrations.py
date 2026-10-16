#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Licensed under Apache-2.0; see LICENSE. No warranties.
"""Initialize the explicitly opted-in local model and independent n8n connector."""

from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen

from configure import read_env

ROOT = Path(__file__).resolve().parents[1]


def ready(url: str, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(1)
    raise RuntimeError(f"Local integration did not become ready: {url}")


def main() -> None:
    config = read_env(ROOT / ".env")
    model = config.get("LLM_MODEL")
    if not model:
        raise RuntimeError("Run make configure first.")
    subprocess.run(
        ["docker", "compose", "exec", "-T", "ollama", "ollama", "pull", model],
        cwd=ROOT,
        check=True,
    )
    ready("http://localhost:5678/healthz/readiness")
    for arguments in (
        [
            "exec",
            "-T",
            "n8n",
            "n8n",
            "import:workflow",
            "--input=/home/node/workflows/bidweave-approved-sync.json",
        ],
        ["exec", "-T", "n8n", "n8n", "publish:workflow", "--id=BidWeaveApprovedSync"],
        ["restart", "n8n"],
    ):
        subprocess.run(["docker", "compose", *arguments], cwd=ROOT, check=True)
    ready("http://localhost:5678/healthz/readiness")
    print(
        "Local model downloaded; n8n workflow imported, published and ready. No case or approval was changed."
    )


if __name__ == "__main__":
    main()
