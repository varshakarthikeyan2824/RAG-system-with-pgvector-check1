"""A small shop API, practice target for day 19. Top-5 security fixes applied; see TRIAGE.md.

Still open on purpose (listed in TRIAGE.md): MD5 password hashing, wildcard CORS, debug mode,
and the Dockerfile and Compose problems.
"""
import base64
import hashlib
import ipaddress
import logging
import os
import secrets
import socket
import sqlite3
from urllib.parse import urlparse

import httpx
from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("shop")

# Secrets come from the environment, never from the code (fix 4).
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
if not LLM_API_KEY:
    raise RuntimeError("LLM_API_KEY must be set (see .env.example)")
LLM_URL = "https://llm.example.invalid/v1/chat"
# Hosts /fetch may call, comma separated. Empty = nothing allowed (fix 5).
ALLOWED_FETCH_HOSTS = {h.strip() for h in os.environ.get("ALLOWED_FETCH_HOSTS", "").split(",") if h.strip()}

app = FastAPI(debug=True)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db = sqlite3.connect(":memory:", check_same_thread=False)
db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, password TEXT, role TEXT)")
db.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, item TEXT, total REAL)")
db.execute("INSERT INTO users VALUES (1, 'alice', 'alice@example.com', ?, 'admin')", (hashlib.md5(b"alice123").hexdigest(),))
db.execute("INSERT INTO users VALUES (2, 'bob', 'bob@example.com', ?, 'user')", (hashlib.md5(b"bob123").hexdigest(),))
db.execute("INSERT INTO orders VALUES (1, 1, 'desk', 120.0)")
db.execute("INSERT INTO orders VALUES (2, 2, 'chair', 40.0)")

_sessions: dict[str, dict] = {}  # random token -> {"id": ..., "role": ...} (in memory: lost on restart)


class OrderIn(BaseModel):
    user_id: int
    item: str
    total: float


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """Fix 3: every sensitive route needs a real, random session token."""
    scheme, _, token = (authorization or "").partition(" ")
    user = _sessions.get(token) if scheme.lower() == "bearer" else None
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")
    return user


def admin_only(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    return user


@app.post("/login")
def login(name: str = Body(), password: str = Body()):
    digest = hashlib.md5(password.encode()).hexdigest()  # still weak: see TRIAGE.md
    log.info("login attempt name=%s", name)  # the password is no longer logged
    row = db.execute("SELECT id, role FROM users WHERE name = ? AND password = ?", (name, digest)).fetchone()
    if not row:
        return {"ok": False, "token": None}
    token = secrets.token_urlsafe(32)  # not base64(name), which anyone could forge
    _sessions[token] = {"id": row[0], "role": row[1]}
    return {"ok": True, "token": token}


@app.get("/search")
def search(q: str, user: dict = Depends(current_user)):
    # Fix 2: the value is a bound parameter, never part of the SQL text.
    rows = db.execute("SELECT id, name, email FROM users WHERE name LIKE ?", (f"%{q}%",)).fetchall()
    return {"results": rows}


@app.get("/orders/{order_id}")
def get_order(order_id: int, user: dict = Depends(current_user)):
    row = db.execute("SELECT id, user_id, item, total FROM orders WHERE id = ?", (order_id,)).fetchone()
    # Own orders only, unless admin. 404 for both cases so ids cannot be probed.
    if row is None or (row[1] != user["id"] and user["role"] != "admin"):
        raise HTTPException(status_code=404, detail="Order not found")
    return {"id": row[0], "user_id": row[1], "item": row[2], "total": row[3]}


@app.get("/admin/users")
def admin_users(user: dict = Depends(admin_only)):
    # Fix 3: login required, admin only, and the password hash is never returned.
    return db.execute("SELECT id, name, email, role FROM users").fetchall()


def _check_fetch_url(url: str) -> None:
    parts = urlparse(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_FETCH_HOSTS:
        raise HTTPException(status_code=400, detail="URL not allowed")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Host not found") from None
    if any(not ipaddress.ip_address(info[4][0]).is_global for info in infos):
        raise HTTPException(status_code=400, detail="URL not allowed")  # private, loopback, link-local


@app.get("/fetch")
def fetch(url: str, user: dict = Depends(current_user)):
    # Fix 5: allow-list of hosts, https only, public addresses only, no redirects, short timeout.
    # Limit: the name is resolved again by httpx, so DNS rebinding is not fully closed (see TRIAGE.md).
    _check_fetch_url(url)
    return {"body": httpx.get(url, timeout=5, follow_redirects=False).text[:500]}


@app.post("/import")
def import_data(items: list[OrderIn], user: dict = Depends(admin_only)):
    # Fix 1: typed JSON instead of pickle. Pickle runs code chosen by the sender.
    return {"loaded": [item.model_dump() for item in items]}


@app.post("/ask")
def ask(question: str = Body(), user: dict = Depends(current_user)):
    resp = httpx.post(
        LLM_URL,
        json={"prompt": f"You are a shop bot. {question}"},
        headers={"Authorization": f"Bearer {LLM_API_KEY}"},  # key in a header, not in the body
        timeout=10,
    )
    try:
        return {"answer": resp.json()["text"]}
    except (ValueError, KeyError):
        raise HTTPException(status_code=502, detail="Model service error") from None
