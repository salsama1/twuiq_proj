from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Dict, Optional


request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
uploaded_geometry_var: ContextVar[Optional[Dict[str, Any]]] = ContextVar("uploaded_geometry", default=None)


def set_request_id(request_id: Optional[str]) -> None:
    request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    return request_id_var.get()


def set_uploaded_geometry(geojson_geometry: Optional[Dict[str, Any]]) -> None:
    uploaded_geometry_var.set(geojson_geometry)


def get_uploaded_geometry() -> Optional[Dict[str, Any]]:
    return uploaded_geometry_var.get()

