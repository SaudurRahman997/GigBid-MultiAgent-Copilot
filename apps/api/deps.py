"""FastAPI dependencies: the app's services and the signed-in user (tenant)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select

from apps.api import db
from apps.api.security import COOKIE, read_token
from apps.api.service import GraphService


def service(request: Request) -> GraphService:
    return request.app.state.service


def get_user_by_id(request: Request, user_id: str) -> dict | None:
    with request.app.state.service.engine.connect() as c:
        row = c.execute(select(db.users).where(db.users.c.id == user_id)).mappings().first()
    return dict(row) if row else None


def current_user(request: Request) -> dict:
    """Session cookie (browser) or `Authorization: Bearer <jwt>` (API clients)."""
    token = request.cookies.get(COOKIE)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:]
    user_id = read_token(token) if token else None
    user = get_user_by_id(request, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")
    return {"id": user["id"], "email": user["email"], "persona": user["persona"]}


User = Depends(current_user)
Service = Depends(service)
