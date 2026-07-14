"""Clerk authentication for FastAPI.

The frontend attaches a Clerk session JWT as `Authorization: Bearer <token>`.
We verify it (RS256) against Clerk's JWKS for the configured issuer and return
the Clerk user id (the `sub` claim). No bypass / no anonymous access.
"""
from __future__ import annotations

import logging

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings

logger = logging.getLogger("krishimitra.auth")

_bearer = HTTPBearer(auto_error=False)
_jwks_client: PyJWKClient | None = None


def _jwks() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        issuer = settings.clerk_issuer.rstrip("/")
        _jwks_client = PyJWKClient(f"{issuer}/.well-known/jwks.json")
    return _jwks_client


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Return the authenticated Clerk user id, or raise 401/503."""
    if not settings.clerk_issuer:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Auth not configured: set CLERK_ISSUER in backend/.env",
        )
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    token = creds.credentials
    try:
        signing_key = _jwks().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer.rstrip("/"),
            options={"verify_aud": False},  # Clerk session tokens have no fixed aud
        )
    except jwt.PyJWTError as e:
        logger.info("token rejected: %s", e)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject")
    return user_id
