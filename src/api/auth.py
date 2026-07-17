"""Neon Auth proxy and JWT verification endpoints."""

from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import urlsplit

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel, Field


router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)
load_dotenv()


class SignUpRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)


def neon_auth_base_url() -> str:
    value = os.getenv("NEON_AUTH_BASE_URL", "").rstrip("/")
    if not value.startswith("https://"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NEON_AUTH_BASE_URL must be an HTTPS Neon Auth URL",
        )
    return value


def neon_auth_endpoint(path: str) -> str:
    return f"{neon_auth_base_url()}/{path}"


def neon_auth_origin() -> str:
    parts = urlsplit(neon_auth_base_url())
    return f"{parts.scheme}://{parts.netloc}"


@lru_cache
def jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True)


def verify_neon_token(token: str) -> dict[str, object]:
    base_url = neon_auth_base_url()
    origin = neon_auth_origin()
    try:
        key = jwks_client(f"{base_url}/.well-known/jwks.json").get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            key.key,
            algorithms=["EdDSA"],
            audience=origin,
            issuer=origin,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, object]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer access token required")
    return verify_neon_token(credentials.credentials)


async def neon_request(
    request: Request, path: str, payload: dict[str, object] | None = None, method: str = "POST"
) -> Response:
    headers = {"origin": request.headers.get("origin", str(request.base_url).rstrip("/"))}
    if payload is not None:
        headers["content-type"] = "application/json"
    if cookie := request.headers.get("cookie"):
        headers["cookie"] = cookie
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            upstream = await client.request(
                method, neon_auth_endpoint(path), json=payload, headers=headers
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Neon Auth is unavailable") from exc

    response_headers = {
        name: value
        for name in ("set-cookie", "set-auth-jwt")
        if (value := upstream.headers.get(name))
    }
    if "application/json" not in upstream.headers.get("content-type", ""):
        return Response(upstream.content, status_code=upstream.status_code, headers=response_headers)
    return JSONResponse(upstream.json(), status_code=upstream.status_code, headers=response_headers)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(payload: SignUpRequest, request: Request) -> Response:
    return await neon_request(request, "sign-up/email", payload.model_dump())


@router.post("/login")
async def login(payload: LoginRequest, request: Request) -> Response:
    return await neon_request(request, "sign-in/email", payload.model_dump())


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> Response:
    response = await neon_request(request, "sign-out")
    if response.status_code >= 400:
        return response
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=dict(response.headers))


@router.post("/token")
async def token(request: Request) -> Response:
    """Refresh/retrieve a Neon JWT using the Neon Auth session cookie."""
    return await neon_request(request, "get-session", method="GET")


@router.get("/me")
async def me(user: dict[str, object] = Depends(current_user)) -> dict[str, object]:
    return {
        "id": user["sub"],
        "email": user.get("email"),
        "role": user.get("role"),
        "expires_at": user["exp"],
    }
