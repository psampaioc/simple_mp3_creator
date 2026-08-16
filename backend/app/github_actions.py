"""Small GitHub Actions dispatcher used to start an ephemeral media runner."""

from __future__ import annotations

import httpx

from app.settings import settings


def dispatch_media_worker() -> None:
    if not settings.github_actions_token:
        raise RuntimeError("GITHUB_ACTIONS_TOKEN is required for managed worker dispatch")
    url = f"https://api.github.com/repos/{settings.github_repository}/actions/workflows/{settings.github_worker_workflow}/dispatches"
    response = httpx.post(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {settings.github_actions_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"ref": "main"},
        timeout=10.0,
    )
    if response.status_code != 204:
        raise RuntimeError(f"GitHub Actions dispatch failed with HTTP {response.status_code}")
