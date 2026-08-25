# RAPTOR — GitHub public repo connector (SSRF korumalı)
from __future__ import annotations

import httpx

from connectors.ssrf import validate_host  # GitHub API host doğrulama


class GithubRepoConnector:
    def __init__(self, max_bytes: int = 2_000_000, redirects: int = 3) -> None:
        self._client = httpx.AsyncClient(
            timeout=25.0, follow_redirects=False, max_redirects=redirects
        )

    async def repo_activity(self, repo: str) -> dict:
        # repo: "owner/name"
        validate_host("api.github.com")  # SSRF güvenlik kontrolü
        parts = repo.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError("repo 'owner/name' formatında olmalı")
        owner, name = parts[0], parts[1]
        url = f"https://api.github.com/repos/{owner}/{name}"
        resp = await self._client.get(
            url, headers={"Accept": "application/vnd.github+json"}
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "full_name": data.get("full_name"),
            "pushed_at": data.get("pushed_at"),
            "updated_at": data.get("updated_at"),
            "open_issues": data.get("open_issues_count"),
            "default_branch": data.get("default_branch"),
            "html_url": data.get("html_url"),
        }

    async def recent_releases(self, repo: str, per_page: int = 5) -> list[dict]:
        validate_host("api.github.com")
        owner, name = repo.strip("/").split("/")[:2]
        url = f"https://api.github.com/repos/{owner}/{name}/releases"
        resp = await self._client.get(
            url, params={"per_page": per_page},
            headers={"Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        return [
            {"tag_name": r.get("tag_name"), "published_at": r.get("published_at"),
             "name": r.get("name")}
            for r in resp.json()
        ]