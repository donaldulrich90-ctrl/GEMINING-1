"""Messagerie interne + communiqués + bannière défilante — porté depuis app.py.

Persisté dans tenant_data/<tid>/collaboration/ (mêmes fichiers que l'ancienne
app) : messages.json et banner_annonce.json.
"""
import json
import os
import uuid
from datetime import datetime

from . import storage


def _collab_dir(tid):
    d = os.path.join(storage.tenant_dir(tid), "collaboration")
    os.makedirs(d, exist_ok=True)
    return d


def _path(tid, name):
    return os.path.join(_collab_dir(tid), name)


def load_messages(tid):
    p = _path(tid, "messages.json")
    if not os.path.isfile(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get("messages", []) if isinstance(d, dict) else []
    except (OSError, ValueError):
        return []


def _save_messages(tid, msgs):
    with open(_path(tid, "messages.json"), "w", encoding="utf-8") as f:
        json.dump({"messages": msgs}, f, indent=2, ensure_ascii=False)


def add_message(tid, sender, to, body, kind="message"):
    msgs = load_messages(tid)
    msgs.append({"id": uuid.uuid4().hex, "ts": datetime.now().isoformat(),
                 "from": sender, "to": to, "kind": kind, "body": body, "attachments": []})
    _save_messages(tid, msgs)


def _read_state_path(tid):
    return _path(tid, "read_state.json")


def _load_read_state(tid):
    p = _read_state_path(tid)
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def mark_read(tid, username):
    """Mémorise l'instant où l'utilisateur a consulté sa messagerie."""
    if not username:
        return
    state = _load_read_state(tid)
    state[username] = datetime.now().isoformat()
    try:
        with open(_read_state_path(tid), "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def unread_count(tid, username):
    """Nombre de messages visibles reçus après la dernière consultation."""
    if not username:
        return 0
    last = _load_read_state(tid).get(username, "")
    n = 0
    for m in load_messages(tid):
        if m.get("from") == username:
            continue  # ses propres messages ne comptent pas
        if not visible_for_user(m, username):
            continue
        if str(m.get("ts", "")) > str(last):
            n += 1
    return n


def visible_for_user(msg, username):
    if msg.get("kind") == "communique" and msg.get("to") == "__all__":
        return True
    if msg.get("kind") == "message" and msg.get("to") == "__team__":
        return True
    return msg.get("to") == username or msg.get("from") == username


def load_banner(tid):
    p = _path(tid, "banner_annonce.json")
    default = {"text": "", "active": True, "ts": ""}
    if not os.path.isfile(p):
        return default
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return {"text": str(d.get("text", "")), "active": bool(d.get("active", True)),
                "ts": str(d.get("ts", ""))}
    except (OSError, ValueError):
        return default


def save_banner(tid, text, active=True):
    with open(_path(tid, "banner_annonce.json"), "w", encoding="utf-8") as f:
        json.dump({"text": str(text or "").strip(), "active": bool(active),
                   "ts": datetime.now().isoformat()}, f, indent=2, ensure_ascii=False)


def _clean(txt, max_len=140):
    s = str(txt or "")
    for t in ("**", "__", "##", "#", "`", ">"):
        s = s.replace(t, "")
    s = " ".join(s.split()).strip()
    return (s[:max_len].rstrip() + "…") if len(s) > max_len else s


def get_marquee(tid, max_communiques=5):
    items = []
    b = load_banner(tid)
    if b.get("active") and b.get("text", "").strip():
        for line in b["text"].splitlines():
            c = _clean(line)
            if c:
                items.append(c)
    communs = [m for m in load_messages(tid)
               if m.get("kind") == "communique" and m.get("to") == "__all__"]
    communs.sort(key=lambda x: x.get("ts", ""), reverse=True)
    for c in communs[:max_communiques]:
        cl = _clean(c.get("body", ""))
        if cl:
            items.append(cl)
    return items
