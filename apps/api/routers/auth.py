from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from apps.api import db
from apps.api.deps import User
from apps.api.schemas import Credentials, Me, Register, Session
from apps.api.security import COOKIE, hash_password, issue_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _session(response: Response, user: dict) -> Session:
    token = issue_token(user["id"])
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=12 * 3600)
    return Session(user=Me(id=user["id"], email=user["email"], persona=user["persona"]), token=token)


def create_user(engine, email: str, password: str, persona: str) -> dict:
    user = {"id": f"u_{uuid.uuid4().hex[:12]}", "email": email.lower(), "persona": persona}
    with engine.begin() as c:
        c.execute(db.users.insert().values(**user, password_hash=hash_password(password)))
    return user


@router.post("/register", response_model=Session, status_code=201)
def register(body: Register, request: Request, response: Response) -> Session:
    try:
        user = create_user(request.app.state.service.engine, body.email, body.password, body.persona)
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered") from None
    return _session(response, user)


@router.post("/login", response_model=Session)
def login(body: Credentials, request: Request, response: Response) -> Session:
    with request.app.state.service.engine.connect() as c:
        row = c.execute(select(db.users).where(db.users.c.email == body.email.lower())).mappings().first()
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong email or password")
    return _session(response, dict(row))


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie(COOKIE)
    response.status_code = 204
    return response


@router.get("/me", response_model=Me)
def me(user: dict = User) -> Me:
    return Me(**user)
