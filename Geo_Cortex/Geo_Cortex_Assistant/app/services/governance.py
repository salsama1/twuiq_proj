from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from app.services.request_context import get_request_id


BASE_DIR = Path(__file__).resolve().parents[2]
AUDIT_LOG_PATH = BASE_DIR / "audit.log"
AUDIT_LOG_DIR = AUDIT_LOG_PATH.parent


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "on")


def governance_enabled() -> bool:
    # Enable audit logging + sanitization
    return _env_flag("DATA_GOVERNANCE", "1")


def strict_mode() -> bool:
    # If strict, sensitive actions can be disabled unless explicitly enabled.
    return _env_flag("DATA_GOV_STRICT", "0")


def feature_enabled(feature: str) -> bool:
    """
    Feature switches. In strict mode, require explicit enable flags.
    In non-strict mode, allow exports/queries by default and only gate ingestion (handled elsewhere too).
    """
    feature = feature.lower()
    if not strict_mode():
        return True
    # strict: require explicit allow
    return _env_flag(f"{feature.upper()}_ENABLE", "0")


_SECRET_PATTERNS = [
    # SQLAlchemy URLs with user:pass@
    re.compile(r"(postgresql\+\w+://)([^:\s]+):([^@\s]+)@"),
    re.compile(r"(postgresql://)([^:\s]+):([^@\s]+)@"),
    # common token-ish strings
    re.compile(r"(api[_-]?key\s*=\s*)([^\s]+)", re.IGNORECASE),
    re.compile(r"(token\s*=\s*)([^\s]+)", re.IGNORECASE),
]


def sanitize_text(text: str) -> str:
    """
    Best-effort redaction to prevent accidental leakage of credentials/paths.
    """
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(lambda m: f"{m.group(1)}***@", out) if "@" in pat.pattern else pat.sub(lambda m: f"{m.group(1)}***", out)
    # Avoid leaking local absolute paths in answers
    out = re.sub(r"[A-Za-z]:\\\\[^\\s\"']+", "[REDACTED_PATH]", out)
    return out


def audit_log(event: str, details: Dict[str, Any], actor: Optional[Dict[str, Any]] = None) -> None:
    """
    Append a JSON line to audit.log (never raises).
    actor: e.g. {"ip": "...", "user_agent": "...", "request_id": "..."}
    """
    if not governance_enabled():
        return
    try:
        # Rotate if file grows too large (best-effort; never raises)
        max_bytes = int(os.getenv("AUDIT_LOG_MAX_BYTES", "5242880"))  # 5MB default
        max_files = int(os.getenv("AUDIT_LOG_MAX_FILES", "5"))
        try:
            if max_bytes > 0 and AUDIT_LOG_PATH.exists() and AUDIT_LOG_PATH.stat().st_size >= max_bytes:
                ts = int(time.time())
                rotated = AUDIT_LOG_DIR / f"audit.{ts}.log"
                AUDIT_LOG_PATH.rename(rotated)
                # cleanup oldest rotations
                if max_files > 0:
                    olds = sorted(AUDIT_LOG_DIR.glob("audit.*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
                    for p in olds[max_files:]:
                        try:
                            p.unlink()
                        except Exception:
                            pass
        except Exception:
            pass

        actor_obj: Dict[str, Any] = dict(actor or {})
        rid = get_request_id()
        if rid and "request_id" not in actor_obj:
            actor_obj["request_id"] = rid
        rec = {
            "ts": time.time(),
            "event": event,
            "actor": actor_obj,
            "details": details,
        }
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        # governance must never break API
        return

