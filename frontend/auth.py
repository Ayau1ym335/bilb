"""
frontend/auth.py  —  Authorization Layer
══════════════════════════════════════════
· Login wall: HMAC-SHA256 password hashes, session TTL 8h
· Roles: admin / operator / viewer
· Building registration form (pre-scan intake)
· Sidebar user widget
· All CSS: dark/technical (#080a0e base, #00ff88 accent)

Usage in every page:
    from frontend.auth import require_auth, current_user, render_sidebar_user
    require_auth()                    # any authenticated user
    require_auth("operate")           # operator / admin only
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import requests as _requests
import streamlit as st

# ──────────────────────────────────────────────────────────────
#  Config
# ──────────────────────────────────────────────────────────────
USERS_FILE  = Path(os.getenv("USERS_FILE", "data/users.json"))
SESSION_TTL = 60 * 60 * 8          # 8 hours
SECRET_KEY  = os.getenv("SECRET_KEY", "bilb-secret-change-in-prod")
API_URL     = os.getenv("API_URL",    "http://localhost:8000")

ROLE_PERMS = {
    "admin":    {"view", "operate", "scan", "report", "admin"},
    "operator": {"view", "operate", "scan", "report"},
    "viewer":   {"view"},
}
ROLE_COLOR = {"admin": "#ff3355", "operator": "#00ff88", "viewer": "#00aaff"}

# ──────────────────────────────────────────────────────────────
#  Dataclass
# ──────────────────────────────────────────────────────────────
@dataclass
class User:
    username:  str
    role:      str
    full_name: str = ""

# ──────────────────────────────────────────────────────────────
#  Password
# ──────────────────────────────────────────────────────────────
def _hash(pw: str) -> str:
    return hmac.new(SECRET_KEY.encode(), pw.encode(), hashlib.sha256).hexdigest()

def _check(pw: str, hashed: str) -> bool:
    return hmac.compare_digest(_hash(pw), hashed)

# ──────────────────────────────────────────────────────────────
#  User store
# ──────────────────────────────────────────────────────────────
def _load() -> dict:
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text())
    except Exception:
        return {}

def _save(users: dict):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2))

def _ensure_defaults():
    if USERS_FILE.exists():
        return
    _save({
        "admin":    {"pw": _hash("bilb2026"), "role": "admin",    "full_name": "Administrator"},
        "operator": {"pw": _hash("operator"), "role": "operator", "full_name": "Field Operator"},
        "demo":     {"pw": _hash("demo"),     "role": "viewer",   "full_name": "Demo User"},
    })

# ──────────────────────────────────────────────────────────────
#  Session
# ──────────────────────────────────────────────────────────────
def _login(username: str, password: str) -> Optional[User]:
    users = _load()
    entry = users.get(username.lower().strip())
    if not entry or not _check(password, entry["pw"]):
        return None
    return User(username=username.lower().strip(),
                role=entry.get("role", "viewer"),
                full_name=entry.get("full_name", username))

def logout():
    for k in ("_auth", "_auth_ts"):
        st.session_state.pop(k, None)

def current_user() -> Optional[User]:
    auth = st.session_state.get("_auth")
    if not auth:
        return None
    if time.time() - st.session_state.get("_auth_ts", 0) > SESSION_TTL:
        logout()
        return None
    return User(**auth)

def has_perm(perm: str) -> bool:
    u = current_user()
    return u is not None and perm in ROLE_PERMS.get(u.role, set())

# ──────────────────────────────────────────────────────────────
#  CSS injected once
# ──────────────────────────────────────────────────────────────
_CSS_INJECTED = False

def _inject_global_css():
    global _CSS_INJECTED
    if _CSS_INJECTED:
        return
    _CSS_INJECTED = True
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&family=Barlow+Condensed:wght@400;600;700;800&display=swap');
:root{
  --bg:#080a0e;--bg2:#0d1117;--bg3:#111820;
  --border:#1e2d3d;--border2:#243447;
  --acc:#00ff88;--warn:#ffaa00;--crit:#ff3355;--info:#00aaff;
  --text:#c8d8e8;--text2:#6a8090;--text3:#3a5060;
  --mono:'JetBrains Mono',monospace;
  --display:'Barlow Condensed',sans-serif;
}
html,body,[data-testid="stAppViewContainer"]{
  background:var(--bg)!important;
  font-family:var(--mono)!important;
  color:var(--text)!important;
}
[data-testid="stSidebar"]{
  background:#0a0d12!important;
  border-right:1px solid var(--border)!important;
}
[data-testid="stSidebar"] *{color:var(--text)!important}
h1{font-family:var(--display)!important;font-size:2rem!important;
   font-weight:800!important;letter-spacing:3px!important;color:var(--text)!important}
h2,h3{font-family:var(--display)!important;font-weight:600!important;
      letter-spacing:2px!important;color:var(--text2)!important}
[data-testid="metric-container"]{
  background:var(--bg2)!important;border:1px solid var(--border)!important;
  border-top:2px solid var(--acc)!important;border-radius:2px!important}
[data-testid="stMetricValue"]{
  font-family:var(--mono)!important;font-size:1.4rem!important;color:var(--acc)!important}
[data-testid="stMetricLabel"]{
  font-family:var(--mono)!important;font-size:.65rem!important;
  letter-spacing:2px!important;color:var(--text2)!important}
.stButton>button{
  background:transparent!important;border:1px solid var(--border2)!important;
  color:var(--text)!important;font-family:var(--mono)!important;
  font-size:.75rem!important;letter-spacing:1px!important;border-radius:2px!important}
.stButton>button:hover{border-color:var(--acc)!important;color:var(--acc)!important}
.stButton>button[kind="primary"]{border-color:var(--acc)!important;color:var(--acc)!important}
.stTextInput>div>div>input,.stSelectbox>div>div,.stNumberInput>div>div>input{
  background:var(--bg2)!important;border:1px solid var(--border)!important;
  border-radius:2px!important;color:var(--text)!important;
  font-family:var(--mono)!important;font-size:.8rem!important}
hr{border-color:var(--border)!important}
/* Scanlines */
body::after{content:'';position:fixed;inset:0;
  background:repeating-linear-gradient(0deg,transparent,transparent 2px,
    rgba(0,0,0,.04) 2px,rgba(0,0,0,.04) 4px);
  pointer-events:none;z-index:9999}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
#  Login page render
# ──────────────────────────────────────────────────────────────
def _render_login():
    _ensure_defaults()
    _inject_global_css()

    # Hide sidebar and header on login page
    st.markdown("""
<style>
[data-testid="stSidebar"]{display:none!important}
#MainMenu,footer,header{visibility:hidden}
.block-container{max-width:440px;margin:0 auto;padding-top:8vh}
</style>""", unsafe_allow_html=True)

    st.markdown("""
<div style="text-align:center;margin-bottom:2rem">
  <div style="font-family:'Barlow Condensed',sans-serif;font-size:3.5rem;
              font-weight:800;letter-spacing:10px;color:#00ff88;
              text-shadow:0 0 30px rgba(0,255,136,.2)">BILB</div>
  <div style="font-size:.7rem;letter-spacing:3px;color:#3a5060;margin-top:2px">
    BUILDING INSPECTION PLATFORM
  </div>
</div>
<div style="background:#0d1117;border:1px solid #1e2d3d;border-top:2px solid #00ff88;
            padding:2rem;border-radius:2px">
""", unsafe_allow_html=True)

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("USERNAME", placeholder="username")
        password = st.text_input("PASSWORD", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("AUTHENTICATE →",
                                          use_container_width=True, type="primary")

    st.markdown("""
  <div style="background:#080a0e;border:1px solid #1e2d3d;padding:.8rem 1rem;
              margin-top:1.2rem;font-size:.7rem;color:#3a5060;border-radius:2px">
    <div style="letter-spacing:1px;margin-bottom:4px">DEFAULT CREDENTIALS</div>
    <div>admin / <span style="color:#00aaff">bilb2026</span> — full access</div>
    <div>operator / <span style="color:#00aaff">operator</span> — robot control</div>
    <div>demo / <span style="color:#00aaff">demo</span> — view only</div>
  </div>
</div>
""", unsafe_allow_html=True)

    if submitted:
        if not username or not password:
            st.error("Enter username and password.")
        else:
            user = _login(username, password)
            if user:
                st.session_state["_auth"]    = asdict(user)
                st.session_state["_auth_ts"] = time.time()
                st.rerun()
            else:
                st.error("Invalid credentials.")

# ──────────────────────────────────────────────────────────────
#  require_auth — main guard
# ──────────────────────────────────────────────────────────────
def require_auth(perm: str = "view"):
    _ensure_defaults()
    _inject_global_css()
    u = current_user()
    if u is None:
        _render_login()
        st.stop()
    if perm and not has_perm(perm):
        st.error(f"Access denied. Required: `{perm}`")
        st.stop()

# ──────────────────────────────────────────────────────────────
#  Sidebar user widget
# ──────────────────────────────────────────────────────────────
def render_sidebar_user():
    u = current_user()
    if not u:
        return
    rc = ROLE_COLOR.get(u.role, "#6a8090")
    st.sidebar.markdown(f"""
<div style="background:#080a0e;border:1px solid #1e2d3d;
            padding:10px 12px;border-radius:2px;margin-bottom:8px">
  <div style="font-size:.65rem;color:#3a5060;letter-spacing:2px;margin-bottom:4px">
    LOGGED IN AS
  </div>
  <div style="font-weight:700;color:#c8d8e8;font-size:.9rem">{u.full_name}</div>
  <div style="display:inline-block;margin-top:4px;padding:1px 8px;
              border:1px solid {rc};color:{rc};font-size:.65rem;
              font-family:'Courier New',monospace;letter-spacing:2px">
    {u.role.upper()}
  </div>
</div>
""", unsafe_allow_html=True)
    if st.sidebar.button("LOGOUT", use_container_width=True):
        logout()
        st.rerun()

# ──────────────────────────────────────────────────────────────
#  Building registration form
# ──────────────────────────────────────────────────────────────
def render_building_form() -> bool:
    """
    Shows the building registration form if no building is registered.
    Returns True if already registered (caller can proceed with scan).
    """
    if st.session_state.get("_building_registered"):
        return True

    st.markdown("""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-top:2px solid #00ff88;
            padding:20px 24px;margin-bottom:24px;border-radius:2px">
  <div style="font-family:'Barlow Condensed',sans-serif;font-size:.9rem;
              letter-spacing:3px;color:#6a8090;margin-bottom:12px">
    ▸ REGISTER BUILDING BEFORE SCAN
  </div>
""", unsafe_allow_html=True)

    with st.form("building_form"):
        c1, c2 = st.columns(2)
        name   = c1.text_input("Building Name *", placeholder="Dom Kultury Vostok")
        city   = c2.text_input("City *",          placeholder="Almaty")
        c3, c4, c5 = st.columns(3)
        year   = c3.number_input("Year Built *", 1800, 2025, 1952)
        area   = c4.number_input("Floor Area (m²)", 50, 50000, 500)
        floors = c5.number_input("Floors", 1, 30, 4)
        addr   = st.text_input("Address", placeholder="ul. Alatau 1")

        ok = st.form_submit_button("REGISTER BUILDING →",
                                   type="primary", use_container_width=True)
        if ok:
            if not name or not city:
                st.error("Name and city are required.")
            else:
                bid = os.getenv("BUILDING_ID", "BILB_001")
                # Persist to DB via FastAPI so all downstream endpoints work
                try:
                    resp = _requests.post(
                        f"{API_URL}/api/buildings",
                        json={
                            "building_id": bid,
                            "name":        name,
                            "city":        city,
                            "address":     addr or None,
                            "year_built":  int(year),
                            "area_m2":     float(area),
                            "floors":      int(floors),
                        },
                        timeout=5,
                    )
                    if not resp.ok:
                        st.warning(f"API registration failed ({resp.status_code}) — "
                                   "running in local-only mode.")
                except Exception as e:
                    st.warning(f"Could not reach API ({e}) — running in local-only mode.")

                for k, v in [("building_name", name), ("building_city", city),
                              ("building_year", year), ("building_area", area),
                              ("building_floors", floors), ("building_addr", addr)]:
                    st.session_state[k] = v
                st.session_state["_building_registered"] = True
                st.success(f"Building '{name}' registered.")
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    return False

def building_meta() -> dict:
    return {
        "name":      st.session_state.get("building_name",  "—"),
        "city":      st.session_state.get("building_city",  "—"),
        "year_built":st.session_state.get("building_year",  1952),
        "area_m2":   st.session_state.get("building_area",  500),
        "floors":    st.session_state.get("building_floors", 4),
        "address":   st.session_state.get("building_addr",  ""),
        "building_id": os.getenv("BUILDING_ID", "BILB_001"),
    }
