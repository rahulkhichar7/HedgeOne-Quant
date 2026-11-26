"""Security groups (playlists) and the full security list."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..data import groups, store
from .common import SafeJSON, fail

router = APIRouter(prefix="/api", tags=["groups"], default_response_class=SafeJSON)


class GroupNew(BaseModel):
    name: str
    members: list[str] = []


class GroupEdit(BaseModel):
    name: str | None = None
    members: list[str] | None = None
    add: list[str] | None = None
    remove: list[str] | None = None


class GroupOrder(BaseModel):
    ids: list[str]


@router.get("/groups")
def list_groups():
    return {"groups": groups.all_groups()}


@router.post("/groups")
def new_group(req: GroupNew):
    try:
        return groups.create(req.name, req.members)
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.patch("/groups/{gid}")
def edit_group(gid: str, req: GroupEdit):
    try:
        return groups.update(gid, req.name, req.members, req.add, req.remove)
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.delete("/groups/{gid}")
def delete_group(gid: str):
    try:
        groups.delete(gid)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        fail(e)


@router.post("/groups-order")
def order_groups(req: GroupOrder):
    return {"groups": groups.reorder(req.ids)}


@router.get("/catalog/status")
def catalog_status():
    return store.catalog_status()


@router.post("/catalog/refresh")
def catalog_refresh():
    started = store.start_catalog_build(force=True)
    return {"started": started, **store.catalog_status()}
