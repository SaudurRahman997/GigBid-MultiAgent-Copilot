"""Portfolio uploads. Agents never read these directly: the Portfolio MCP server serves them to
the same user's runs (rag/uploads.py)."""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, HTTPException, Response

from apps.api.deps import User
from apps.api.schemas import UploadIn, UploadOut
from rag import uploads

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _out(item: uploads.Upload) -> UploadOut:
    return UploadOut(
        id=item.id,
        filename=item.filename,
        type=item.type,
        title=item.title,
        characters=len(item.text),
    )


@router.get("/uploads", response_model=list[UploadOut])
def list_uploads(user: dict = User) -> list[UploadOut]:
    return [_out(u) for u in uploads.list_uploads(user["persona"], user["id"])]


@router.post("/uploads", response_model=UploadOut, status_code=201)
def add_upload(body: UploadIn, user: dict = User) -> UploadOut:
    try:
        data = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "content_base64 is not valid base64") from None
    try:
        return _out(uploads.save_upload(user["persona"], user["id"], body.filename, data))
    except uploads.UploadError as exc:
        raise HTTPException(422, str(exc)) from None
    except OSError:
        raise HTTPException(503, "uploads cannot be stored on this server") from None


@router.delete("/uploads/{upload_id}", status_code=204)
def remove_upload(upload_id: str, user: dict = User) -> Response:
    if not uploads.delete_upload(user["persona"], user["id"], upload_id):
        raise HTTPException(404, "upload not found")
    return Response(status_code=204)
