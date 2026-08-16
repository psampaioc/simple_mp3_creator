"""Supabase JWT verification for the managed API boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.settings import settings


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: str
    access_token: str = ""


bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _jwks() -> dict[str, object]:
    if not settings.supabase_url:
        raise RuntimeError("SUPABASE_URL is required for managed authentication")
    response = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json",
        timeout=5.0,
    )
    response.raise_for_status()
    return response.json()


def _decode_token(token: str) -> dict[str, object]:
    header = jwt.get_unverified_header(token)
    key_id = header.get("kid")
    key_data = next((key for key in _jwks().get("keys", []) if key.get("kid") == key_id), None)
    if key_data is None:
        _jwks.cache_clear()
        key_data = next((key for key in _jwks().get("keys", []) if key.get("kid") == key_id), None)
    if key_data is None:
        raise ValueError("token signing key not found")
    issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
    algorithm = header.get("alg", "RS256")
    key_type = key_data.get("kty")
    if key_type == "EC":
        signing_key = jwt.algorithms.ECAlgorithm.from_jwk(json.dumps(key_data))
    elif key_type == "RSA":
        signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
    else:
        raise ValueError("unsupported token signing key")
    return jwt.decode(token, signing_key, algorithms=[algorithm], audience="authenticated", issuer=issuer)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    try:
        claims = _decode_token(credentials.credentials)
        user_id = claims.get("sub")
        role = claims.get("role")
        if not isinstance(user_id, str) or not isinstance(role, str):
            raise ValueError("token subject or role is invalid")
        return CurrentUser(id=user_id, role=role, access_token=credentials.credentials)
    except (httpx.HTTPError, jwt.PyJWTError, ValueError, KeyError, RuntimeError) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid authentication token") from error


def optional_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> CurrentUser | None:
    """Keep the local adapter anonymous while requiring auth in managed mode."""
    if credentials is None:
        return None
    return current_user(credentials)
