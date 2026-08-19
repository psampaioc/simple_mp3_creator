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
    def __init__(self, project_url: str, publishable_key: str, transport: httpx.BaseTransport | None = None, secret_key: str = "", service_role_key: str = "") -> None:
        if not project_url or not publishable_key:
            raise ValueError("Supabase URL and publishable key are required")
        self.base_url = f"{project_url.rstrip('/')}/rest/v1"
        self.storage_url = f"{project_url.rstrip('/')}/storage/v1"
        self.publishable_key = publishable_key
        self.secret_key = secret_key or service_role_key
        self.transport = transport

    def _headers(self, access_token: str) -> dict[str, str]:
        return {
            "apikey": self.publishable_key,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def _service_headers(self) -> dict[str, str]:
        if not self.secret_key:
            raise ValueError("SUPABASE_SECRET_KEY is required for cleanup operations")
        return {"apikey": self.secret_key, "Authorization": f"Bearer {self.secret_key}"}

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
            params={"select": "*", "expires_at": "gt.now()", "order": "created_at.desc"},
        )
        rows = response.json()
        if not isinstance(rows, list):
            raise SupabaseAPIError("Supabase returned an unexpected project list")
        return rows

    def count_projects_since(self, access_token: str, created_since: str) -> int:
        response = self._request(
            "GET",
            "projects",
            access_token,
            params={"select": "id", "created_at": f"gte.{created_since}"},
            headers={"Prefer": "count=exact"},
        )
        count = response.headers.get("content-range", "").split("/")[-1]
        if not count.isdigit():
            raise SupabaseAPIError("Supabase did not return a project count")
        return int(count)

    def create_job(self, access_token: str, job: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST",
            "jobs",
            access_token,
            params={"select": "*"},
            headers={"Prefer": "return=representation"},
            json=job,
        )
        rows = response.json()
        if not isinstance(rows, list) or len(rows) != 1:
            raise SupabaseAPIError("Supabase returned an unexpected job response")
        return rows[0]

    def claim_next_job_service(self, worker_id: str, job_id: str = "") -> dict[str, Any] | None:
        payload: dict[str, Any] = {"p_worker_id": worker_id, "p_job_id": job_id or None}
        response = self._service_request("POST", "rpc/claim_next_job", json=payload)
        payload = response.json()
        return payload if isinstance(payload, dict) and payload else None

    def cleanup_stale_jobs_service(self, queued_timeout_seconds: int = 120, running_timeout_seconds: int = 900) -> int:
        response = self._service_request(
            "POST",
            "rpc/cleanup_stale_jobs",
            json={
                "p_queue_timeout_seconds": queued_timeout_seconds,
                "p_running_timeout_seconds": running_timeout_seconds,
            },
        )
        result = response.json()
        return int(result) if isinstance(result, int) else 0

    def update_job_service(self, job_id: str, values: dict[str, Any]) -> None:
        self._service_request("PATCH", "jobs", params={"id": f"eq.{job_id}"}, json=values)

    def get_job_service(self, project_id: str) -> dict[str, Any] | None:
        response = self._service_request("GET", "jobs", params={"select": "*", "project_id": f"eq.{project_id}", "limit": "1"})
        rows = response.json()
        if not isinstance(rows, list):
            raise SupabaseAPIError("Supabase returned an unexpected job response")
        return rows[0] if rows else None

    def get_project_service(self, project_id: str) -> dict[str, Any] | None:
        response = self._service_request("GET", "projects", params={"select": "*", "id": f"eq.{project_id}", "limit": "1"})
        rows = response.json()
        if not isinstance(rows, list):
            raise SupabaseAPIError("Supabase returned an unexpected project response")
        return rows[0] if rows else None

    def get_project(self, access_token: str, project_id: str) -> dict[str, Any] | None:
        response = self._request(
            "GET",
            "projects",
            access_token,
            params={"select": "*", "id": f"eq.{project_id}", "expires_at": "gt.now()", "limit": "1"},
        )
        rows = response.json()
        if not isinstance(rows, list):
            raise SupabaseAPIError("Supabase returned an unexpected project response")
        return rows[0] if rows else None

    def update_project(self, access_token: str, project_id: str, values: dict[str, Any]) -> None:
        self._request("PATCH", "projects", access_token, params={"id": f"eq.{project_id}"}, json=values)

    def upload_asset(self, access_token: str, storage_path: str, content: bytes, content_type: str = "audio/mpeg") -> None:
        with httpx.Client(transport=self.transport, timeout=30.0) as client:
            response = client.post(
                f"{self.storage_url}/object/project-assets/{storage_path}",
                headers={**self._headers(access_token), "x-upsert": "true"},
                content=content,
            )
        if response.is_error:
            raise SupabaseAPIError(f"Supabase asset upload returned HTTP {response.status_code}")

    def create_signed_upload_url(self, access_token: str, storage_path: str, expires_in: int = 7200) -> dict[str, str]:
        with httpx.Client(transport=self.transport, timeout=10.0) as client:
            response = client.post(
                f"{self.storage_url}/object/upload/sign/project-assets/{storage_path}",
                headers=self._headers(access_token),
                json={"upsert": False},
            )
        if response.is_error:
            raise SupabaseAPIError(f"Supabase signed upload URL returned HTTP {response.status_code}")
        payload = response.json()
        token = payload.get("token")
        signed_url = payload.get("signedURL") or payload.get("url")
        if not isinstance(token, str) or not token:
            raise SupabaseAPIError("Supabase returned an unexpected signed upload token")
        result = {"path": storage_path, "token": token}
        if isinstance(signed_url, str) and signed_url:
            result["url"] = signed_url
        return result

    def update_project_service(self, project_id: str, values: dict[str, Any]) -> None:
        with httpx.Client(transport=self.transport, timeout=10.0) as client:
            response = client.patch(
                f"{self.base_url}/projects",
                headers={**self._service_headers(), "Content-Type": "application/json"},
                params={"id": f"eq.{project_id}"},
                json=values,
            )
        if response.is_error:
            raise SupabaseAPIError(f"Supabase project update returned HTTP {response.status_code}")

    def record_generation_error_service(self, error: dict[str, Any]) -> None:
        self._service_request("POST", "generation_errors", json=error)

    def upload_asset_service(self, storage_path: str, content: bytes, content_type: str = "audio/mpeg") -> None:
        with httpx.Client(transport=self.transport, timeout=30.0) as client:
            response = client.post(
                f"{self.storage_url}/object/project-assets/{storage_path}",
                headers={**self._service_headers(), "Content-Type": content_type, "x-upsert": "true"},
                content=content,
            )
        if response.is_error:
            raise SupabaseAPIError(f"Supabase asset upload returned HTTP {response.status_code}")

    def download_asset_service(self, storage_path: str, max_bytes: int) -> bytes:
        with httpx.Client(transport=self.transport, timeout=30.0) as client:
            response = client.get(
                f"{self.storage_url}/object/project-assets/{storage_path}",
                headers=self._service_headers(),
            )
        if response.is_error:
            raise SupabaseAPIError(f"Supabase asset download returned HTTP {response.status_code}")
        if len(response.content) > max_bytes:
            raise SupabaseAPIError("Supabase asset exceeds the configured size limit")
        return response.content

    def create_asset_service(self, asset: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(transport=self.transport, timeout=10.0) as client:
            response = client.post(
                f"{self.base_url}/assets",
                headers={**self._service_headers(), "Content-Type": "application/json", "Prefer": "return=representation"},
                json=asset,
            )
        if response.is_error:
            raise SupabaseAPIError(f"Supabase asset record returned HTTP {response.status_code}")
        rows = response.json()
        if not isinstance(rows, list) or len(rows) != 1:
            raise SupabaseAPIError("Supabase returned an unexpected asset response")
        return rows[0]

    def create_asset(self, access_token: str, asset: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", "assets", access_token, params={"select": "*"}, headers={"Prefer": "return=representation"}, json=asset)
        rows = response.json()
        if not isinstance(rows, list) or len(rows) != 1:
            raise SupabaseAPIError("Supabase returned an unexpected asset response")
        return rows[0]

    def get_mp3_asset(self, access_token: str, project_id: str) -> dict[str, Any] | None:
        response = self._request(
            "GET",
            "assets",
            access_token,
            params={"select": "*", "project_id": f"eq.{project_id}", "kind": "eq.mp3", "expires_at": "gt.now()", "order": "created_at.desc", "limit": "1"},
        )
        rows = response.json()
        if not isinstance(rows, list):
            raise SupabaseAPIError("Supabase returned an unexpected asset response")
        return rows[0] if rows else None

    def create_signed_url(self, access_token: str, storage_path: str, expires_in: int = 900) -> str:
        with httpx.Client(transport=self.transport, timeout=10.0) as client:
            response = client.post(
                f"{self.storage_url}/object/sign/project-assets/{storage_path}",
                headers=self._headers(access_token),
                json={"expiresIn": expires_in},
            )
        if response.is_error:
            raise SupabaseAPIError(f"Supabase signed URL returned HTTP {response.status_code}")
        signed_url = response.json().get("signedURL")
        if not isinstance(signed_url, str) or not signed_url:
            raise SupabaseAPIError("Supabase returned an unexpected signed URL response")
        return f"{self.storage_url}{signed_url}" if signed_url.startswith("/") else signed_url

    def list_expired_assets_service(self) -> list[dict[str, Any]]:
        response = self._service_request("GET", "assets", params={"select": "id,project_id,storage_path", "expires_at": "lt.now()", "limit": "1000"})
        rows = response.json()
        if not isinstance(rows, list):
            raise SupabaseAPIError("Supabase returned an unexpected expired asset response")
        return rows

    def list_expired_projects_service(self) -> list[dict[str, Any]]:
        response = self._service_request("GET", "projects", params={"select": "id", "expires_at": "lt.now()", "limit": "1000"})
        rows = response.json()
        if not isinstance(rows, list):
            raise SupabaseAPIError("Supabase returned an unexpected expired project response")
        return rows

    def _service_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {**self._service_headers(), "Content-Type": "application/json"}
        with httpx.Client(transport=self.transport, timeout=30.0) as client:
            response = client.request(method, f"{self.base_url}/{path}", headers=headers, **kwargs)
        if response.is_error:
            raise SupabaseAPIError(f"Supabase service request returned HTTP {response.status_code}")
        return response

    def delete_asset_service(self, asset_id: str) -> None:
        self._service_request("DELETE", "assets", params={"id": f"eq.{asset_id}"})

    def delete_project_service(self, project_id: str) -> None:
        self._service_request("DELETE", "projects", params={"id": f"eq.{project_id}"})

    def delete_storage_object_service(self, storage_path: str) -> None:
        with httpx.Client(transport=self.transport, timeout=30.0) as client:
            response = client.delete(
                f"{self.storage_url}/object/project-assets/{storage_path}",
                headers=self._service_headers(),
            )
        if response.is_error and response.status_code != 404:
            raise SupabaseAPIError(f"Supabase storage delete returned HTTP {response.status_code}")
