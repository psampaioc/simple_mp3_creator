import httpx

from app.supabase_api import SupabaseAPI


def test_supabase_api_sends_user_token_and_parses_project() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["Authorization"]
        seen["apikey"] = request.headers["apikey"]
        assert request.url.path == "/rest/v1/projects"
        return httpx.Response(201, json=[{"id": "project-1", "user_id": "user-1"}])

    api = SupabaseAPI("https://example.supabase.co", "publishable", httpx.MockTransport(handler))
    project = api.create_project("user-token", {"user_id": "user-1"})

    assert project["id"] == "project-1"
    assert seen == {"authorization": "Bearer user-token", "apikey": "publishable"}


def test_supabase_api_creates_signed_url_for_private_asset() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rest/v1/assets":
            return httpx.Response(200, json=[{"storage_path": "user-1/project-1.mp3"}])
        assert request.url.path == "/storage/v1/object/sign/project-assets/user-1/project-1.mp3"
        assert request.headers["Authorization"] == "Bearer user-token"
        return httpx.Response(200, json={"signedURL": "/object/sign/project-assets/user-1/project-1.mp3?token=test"})

    api = SupabaseAPI("https://example.supabase.co", "publishable", httpx.MockTransport(handler))
    asset = api.get_mp3_asset("user-token", "project-1")
    assert asset == {"storage_path": "user-1/project-1.mp3"}
    assert api.create_signed_url("user-token", asset["storage_path"]) == "https://example.supabase.co/storage/v1/object/sign/project-assets/user-1/project-1.mp3?token=test"
