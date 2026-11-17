from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, select

from apps.api import db
from apps.api.deps import Service, User
from apps.api.schemas import AccountStatus, AccountToken, Settings

router = APIRouter(prefix="/settings", tags=["settings"])
PROVIDERS = ("upwork",)


@router.get("", response_model=Settings)
def get_settings(user: dict = User, svc=Service) -> Settings:
    with svc.engine.connect() as c:
        row = c.execute(
            select(db.settings.c.value).where(db.settings.c.tenant_id == user["id"])
        ).first()
    return Settings.model_validate(row[0]) if row else Settings()


@router.put("", response_model=Settings)
def put_settings(body: Settings, user: dict = User, svc=Service) -> Settings:
    with svc.engine.begin() as c:
        c.execute(delete(db.settings).where(db.settings.c.tenant_id == user["id"]))
        c.execute(db.settings.insert().values(tenant_id=user["id"], value=body.model_dump()))
    return body


@router.get("/accounts", response_model=list[AccountStatus])
def accounts(user: dict = User, svc=Service) -> list[AccountStatus]:
    q = select(db.oauth_tokens.c.provider).where(db.oauth_tokens.c.tenant_id == user["id"])
    with svc.engine.connect() as c:
        have = {r[0] for r in c.execute(q)}
    return [AccountStatus(provider=p, connected=p in have) for p in PROVIDERS]


@router.put("/accounts/{provider}", response_model=AccountStatus)
def connect_account(
    provider: str, body: AccountToken, request: Request, user: dict = User, svc=Service
) -> AccountStatus:
    """Stores OAuth tokens encrypted (Fernet). Tokens are never returned by the API."""
    if provider not in PROVIDERS:
        raise HTTPException(404, "unknown provider")
    sealed = request.app.state.vault.seal(body.model_dump())
    t = db.oauth_tokens
    with svc.engine.begin() as c:
        c.execute(delete(t).where(t.c.tenant_id == user["id"], t.c.provider == provider))
        c.execute(t.insert().values(tenant_id=user["id"], provider=provider, ciphertext=sealed))
    return AccountStatus(provider=provider, connected=True)


@router.delete("/accounts/{provider}", response_model=AccountStatus)
def disconnect_account(provider: str, user: dict = User, svc=Service) -> AccountStatus:
    t = db.oauth_tokens
    with svc.engine.begin() as c:
        c.execute(delete(t).where(t.c.tenant_id == user["id"], t.c.provider == provider))
    return AccountStatus(provider=provider, connected=False)
