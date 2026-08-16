"""Small PostgREST client used by the managed backend adapter.

The client intentionally accepts the caller's Supabase access token on every
request so PostgreSQL RLS evaluates ownership as the authenticated user.
"""

from __future__ import annotations

from typing import Any

import httpx


class SupabaseAPIError(RuntimeError):
    """A non-successful Supabase Data API response."""


class SupabaseAPI:
    def __init__(self, project_url: str, publishable_key: str, transport: httpx.BaseTransport | None = None) -> None:
        if not project_url or not publishable_key:
            raise ValueError("Supabase URL and publishable key are required")
        self.base_url = f"{project_url.rstrip('/')}/rest/v1"
        self.publishable_key = publishable_key
        self.transport = transport

    def _headers(self, access_token: str) -> dict[str, str]:
        return {
            "apikey": self.publishable_key,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, access_token: str, **kwargs: Any) -> httpx.Response:
        request_headers = self._headers(access_token)
        request_headers.update(kwargs.pop("headers", {}))
        with httpx.Client(transport=self.transport, timeout=10.0) as client:
            response = client.request(method, f"{self.base_url}/{path}", headers=request_headers, **kwargs)
        if response.is_error:
            raise SupabaseAPIError(f"Supabase Data API returned HTTP {response.status_code}")
        return response

    def create_project(self, access_token: str, project: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST",
            "projects",
            access_token,
            params={"select": "*"},
            headers={"Prefer": "return=representation"},
            json=project,
        )
        rows = response.json()
        if not isinstance(rows, list) or len(rows) != 1:
            raise SupabaseAPIError("Supabase returned an unexpected project response")
        return rows[0]

    def list_projects(self, access_token: str) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            "projects",
            access_token,
            params={"select": "*", "order": "created_at.desc"},
        )
        rows = response.json()
        if not isinstance(rows, list):
            raise SupabaseAPIError("Supabase returned an unexpected project list")
        return rows

    def get_project(self, access_token: str, project_id: str) -> dict[str, Any] | None:
        response = self._request(
            "GET",
            "projects",
            access_token,
            params={"select": "*", "id": f"eq.{project_id}", "limit": "1"},
        )
        rows = response.json()
        if not isinstance(rows, list):
            raise SupabaseAPIError("Supabase returned an unexpected project response")
        return rows[0] if rows else None
