import secrets

from fastapi import Header, HTTPException

from src.config import get_settings


def require_service_key(x_service_key: str = Header(default="")):
    expected = get_settings().service_api_key.get_secret_value()
    if not secrets.compare_digest(x_service_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorised")