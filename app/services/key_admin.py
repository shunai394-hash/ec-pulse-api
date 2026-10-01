import os
import secrets

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from app.services.monitor_store import create_api_key, list_api_keys, revoke_api_key

_admin_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class CreateKeyRequest(BaseModel):
    plan: str = Field(default="free", pattern="^(free|pro|business)$")
    credits: int = Field(default=100, ge=0, le=10_000_000)


class RevokeKeyRequest(BaseModel):
    api_key: str = Field(min_length=16, max_length=200)


def _admin_key(api_key: str | None = Depends(_admin_header)) -> str:
    expected = os.getenv("EC_PULSE_API_KEY")
    if not expected or not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status_code=403, detail="Admin API key required")
    return api_key


def register_key_routes(app: FastAPI) -> None:
    @app.post("/v1/admin/keys", include_in_schema=False)
    def create_key(request: CreateKeyRequest, _: str = Depends(_admin_key)):
        try:
            return create_api_key(request.plan, request.credits)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/v1/admin/keys", include_in_schema=False)
    def keys(_: str = Depends(_admin_key)):
        try:
            return {"keys": list_api_keys()}
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/v1/admin/keys/revoke", include_in_schema=False)
    def revoke(request: RevokeKeyRequest, _: str = Depends(_admin_key)):
        try:
            revoked = revoke_api_key(request.api_key)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if not revoked:
            raise HTTPException(status_code=404, detail="API key not found")
        return {"revoked": True}
