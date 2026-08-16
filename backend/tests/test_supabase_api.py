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
