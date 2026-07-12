from __future__ import annotations

from typing import Any

from .request_id import get_request_id


def ok(data: Any = None, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    m = {"request_id": get_request_id()}
    if meta:
        m.update(meta)
    return {"data": data, "meta": m}


def ok_paginated(
    data: Any,
    *,
    page: int,
    page_size: int,
    total: int,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = ok(data, meta=meta)
    payload["pagination"] = {
        "page": page,
        "page_size": page_size,
        "total": total,
    }
    return payload


def err(code: str, message: str, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {"code": code, "message": message, "details": details or {}},
        "meta": {"request_id": get_request_id()},
    }
