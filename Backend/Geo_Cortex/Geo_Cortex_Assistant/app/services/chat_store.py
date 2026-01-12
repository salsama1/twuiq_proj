from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional
import time

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.dbmodels import AgentSession


Role = Literal["user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str
    ts: float


# In-memory chat store (per-process). Good enough for local UI.
_store: Dict[str, List[ChatMessage]] = {}
_state_store: Dict[str, Dict[str, Any]] = {}


def get_history(session_id: str, limit: int = 12) -> List[ChatMessage]:
    msgs = _store.get(session_id, [])
    if limit <= 0:
        return []
    return msgs[-limit:]


def append_message(session_id: str, role: Role, content: str) -> None:
    if not content:
        return
    msgs = _store.setdefault(session_id, [])
    msgs.append(ChatMessage(role=role, content=content, ts=time.time()))
    # keep last 40 messages
    if len(msgs) > 40:
        _store[session_id] = msgs[-40:]


def reset_session(session_id: str) -> None:
    _store.pop(session_id, None)
    _state_store.pop(session_id, None)


def get_state(session_id: str) -> Dict[str, Any]:
    return _state_store.setdefault(session_id, {})


def set_state_value(session_id: str, key: str, value: Any) -> None:
    st = _state_store.setdefault(session_id, {})
    st[key] = value


def get_state_value(session_id: str, key: str, default: Optional[Any] = None) -> Any:
    st = _state_store.get(session_id) or {}
    return st.get(key, default)


def _get_or_create_db_session(db: Session, session_id: str) -> AgentSession:
    s = db.query(AgentSession).filter(AgentSession.session_id == session_id).first()
    if s is None:
        s = AgentSession(session_id=session_id, messages=[], state={})
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def get_history_db(db: Session, session_id: str, limit: int = 12) -> List[ChatMessage]:
    s = _get_or_create_db_session(db, session_id)
    msgs = list(s.messages or [])
    if limit <= 0:
        return []
    out: List[ChatMessage] = []
    for m in msgs[-limit:]:
        try:
            out.append(ChatMessage(role=m.get("role"), content=m.get("content"), ts=float(m.get("ts") or time.time())))
        except Exception:
            continue
    return out


def append_message_db(db: Session, session_id: str, role: Role, content: str) -> None:
    if not content:
        return
    s = _get_or_create_db_session(db, session_id)
    msgs = list(s.messages or [])
    msgs.append({"role": role, "content": content, "ts": time.time()})
    if len(msgs) > 40:
        msgs = msgs[-40:]
    s.messages = msgs
    s.updated_at = datetime.utcnow()
    db.add(s)
    db.commit()


def reset_session_db(db: Session, session_id: str) -> None:
    db.query(AgentSession).filter(AgentSession.session_id == session_id).delete()
    db.commit()


def get_state_db(db: Session, session_id: str) -> Dict[str, Any]:
    s = _get_or_create_db_session(db, session_id)
    st = dict(s.state or {})
    return st


def get_state_value_db(db: Session, session_id: str, key: str, default: Optional[Any] = None) -> Any:
    st = get_state_db(db, session_id)
    return st.get(key, default)


def set_state_value_db(db: Session, session_id: str, key: str, value: Any) -> None:
    s = _get_or_create_db_session(db, session_id)
    st = dict(s.state or {})
    st[key] = value
    s.state = st
    s.updated_at = datetime.utcnow()
    db.add(s)
    db.commit()

