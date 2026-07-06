import secrets

from fastapi import Header, HTTPException
from config import settings


def require_auth(authorization: str | None = Header(default=None)) -> None:
    expected = settings.SPACENOTE_TOKEN
    if not expected:
        raise HTTPException(status_code=500, detail="SPACENOTE_TOKEN not configured")
    if not authorization or not secrets.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="Invalid or missing token")
