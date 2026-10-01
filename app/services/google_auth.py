import base64
import hashlib
import json
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse


def _config() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    if not url or not key:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    return url, key


def _callback_url() -> str:
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="APP_BASE_URL is not configured")
    return f"{base}/auth/callback"


def _secure_cookie() -> bool:
    base = os.getenv("APP_BASE_URL", "").strip().lower()
    return base.startswith("https://")


def _code_verifier() -> str:
    return secrets.token_urlsafe(64)


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


async def google_login() -> RedirectResponse:
    supabase_url, _ = _config()
    verifier = _code_verifier()
    params = {
        "provider": "google",
        "redirect_to": _callback_url(),
        "code_challenge": _code_challenge(verifier),
        "code_challenge_method": "s256",
    }
    response = RedirectResponse(
        f"{supabase_url}/auth/v1/authorize?{urlencode(params)}",
        status_code=302,
    )
    response.set_cookie(
        "ecp_oauth_verifier",
        verifier,
        max_age=600,
        httponly=True,
        secure=_secure_cookie(),
        samesite="lax",
        path="/auth",
    )
    return response


async def exchange_callback(request: Request, code: str) -> RedirectResponse:
    supabase_url, publishable_key = _config()
    verifier = request.cookies.get("ecp_oauth_verifier")
    if not verifier:
        raise HTTPException(status_code=400, detail="Missing OAuth verifier")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{supabase_url}/auth/v1/token",
            params={"grant_type": "pkce"},
            headers={"apikey": publishable_key},
            json={"auth_code": code, "code_verifier": verifier},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=401, detail="Google login failed")
    session = response.json()
    access_token = session.get("access_token")
    refresh_token = session.get("refresh_token")
    if not access_token or not refresh_token:
        raise HTTPException(status_code=401, detail="Google login returned no session")

    redirect = RedirectResponse("/", status_code=302)
    redirect.delete_cookie("ecp_oauth_verifier", path="/auth")
    # Session tokens must never travel over plain HTTP in production, even if
    # APP_ENV is missing: an https APP_BASE_URL also forces the Secure flag.
    secure = _secure_cookie() or os.getenv("APP_ENV", "development") == "production"
    redirect.set_cookie(
        "ecp_access_token",
        access_token,
        max_age=int(session.get("expires_in", 3600)),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    redirect.set_cookie(
        "ecp_refresh_token",
        refresh_token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    return redirect


async def current_user(request: Request) -> dict:
    supabase_url, publishable_key = _config()
    access_token = request.cookies.get("ecp_access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{supabase_url}/auth/v1/user",
            headers={
                "apikey": publishable_key,
                "Authorization": f"Bearer {access_token}",
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=401, detail="Session expired")
    return response.json()


def logout() -> RedirectResponse:
    response = RedirectResponse("/", status_code=302)
    secure = _secure_cookie() or os.getenv("APP_ENV", "development") == "production"
    response.delete_cookie("ecp_access_token", path="/", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie("ecp_refresh_token", path="/", secure=secure, httponly=True, samesite="lax")
    return response
