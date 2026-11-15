from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from agent.memory.store import KINDS, delete_memory, list_memory
from apps.api.deps import Service, User
from apps.api.schemas import MemoryItem

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=list[MemoryItem])
def all_memory(user: dict = User, svc=Service) -> list[MemoryItem]:
    out = []
    for kind in KINDS:
        for item in list_memory(svc.store, user["id"], kind):
            key = item.pop("key")
            out.append(MemoryItem(namespace=kind, key=key, value=item))
    return out


@router.delete("/{namespace}/{key}", status_code=204)
def forget(namespace: str, key: str, user: dict = User, svc=Service) -> Response:
    if namespace not in KINDS:
        raise HTTPException(404, "unknown memory namespace")
    delete_memory(svc.store, user["id"], namespace, key)
    return Response(status_code=204)
