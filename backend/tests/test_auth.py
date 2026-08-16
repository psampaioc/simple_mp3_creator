import json
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient

from app import auth
from app.main import app


def test_authenticated_identity_accepts_valid_supabase_style_jwt(monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "test-key"
    monkeypatch.setattr(auth.settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(auth, "_jwks", lambda: {"keys": [public_jwk]})
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "role": "authenticated",
            "aud": "authenticated",
            "iss": "https://example.supabase.co/auth/v1",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    response = TestClient(app).get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["role"] == "authenticated"


def test_authenticated_identity_accepts_supabase_ec_jwt(monkeypatch) -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "test-ec-key"
    monkeypatch.setattr(auth.settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(auth, "_jwks", lambda: {"keys": [public_jwk]})
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "role": "authenticated",
            "aud": "authenticated",
            "iss": "https://example.supabase.co/auth/v1",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "test-ec-key"},
    )

    response = TestClient(app).get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
