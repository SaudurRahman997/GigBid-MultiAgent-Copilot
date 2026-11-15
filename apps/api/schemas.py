"""Request/response models for the HTTP API (exported to OpenAPI -> TypeScript client)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Persona = Literal["ai_ml", "fullstack", "data_analyst"]


class Credentials(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)
    password: str = Field(min_length=8, max_length=200)


class Register(Credentials):
    persona: Persona = "ai_ml"


class Me(BaseModel):
    id: str
    email: str
    persona: str


class Session(BaseModel):
    user: Me
    token: str


class Run(BaseModel):
    thread_id: str
    kind: str
    subject: str
    title: str = ""
    status: str
    stage: str | None = None
    tokens: int = 0
    steps: int = 0
    summary: dict[str, Any] = {}
    created_at: str | None = None
    updated_at: str | None = None


class RunDetail(Run):
    state: dict[str, Any]
    next: list[str] = []


class Started(BaseModel):
    thread_id: str
    events_url: str


class PendingApproval(Run):
    request: dict[str, Any]


class Decision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = Field(default=None, max_length=8000)
    reason: str | None = Field(default=None, max_length=500)


class SavedSearch(BaseModel):
    name: str = Field(max_length=80)
    query: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=40)
    every_minutes: int = Field(default=60, ge=30, le=1440)


class Settings(BaseModel):
    autonomy: Literal["suggest", "draft", "approve_each"] = "approve_each"
    daily_connects_budget: int = Field(default=40, ge=0, le=500)
    max_tokens_per_thread: int = Field(default=20000, ge=1000, le=200000)
    saved_searches: list[SavedSearch] = []


class AccountToken(BaseModel):
    access_token: str = Field(min_length=1, max_length=4000)
    refresh_token: str | None = Field(default=None, max_length=4000)
    expires_at: str | None = None


class AccountStatus(BaseModel):
    provider: str
    connected: bool


class MemoryItem(BaseModel):
    namespace: str
    key: str
    value: dict[str, Any]


class Health(BaseModel):
    ok: bool
    degraded: bool
    servers: dict[str, bool]
