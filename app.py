"""
Quinela Mundial 2026 · Posgrado IMP
=====================================
v9 — Tablas por etapa + premios especiales:
  - Rankings separados para fase de grupos y eliminatorias
  - Distinciones automáticas de fase de grupos: más exactos, más aciertos, mejor efectividad, mejor diferencia y participación
  - Pronósticos especiales de eliminatorias/torneo: campeón, Balón de Oro, Bota de Oro, Guante de Oro, Fair Play, caballo negro, etc.
  - Mantiene Supabase, auditoría, bloqueos, exports, seguridad, diseño institucional y calendario de 104 partidos
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

try:
    from supabase import create_client as _sb_create
except Exception:
    _sb_create = None  # type: ignore[assignment]

# ──────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Quinela Mundial 2026 · IMP",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT            = Path(__file__).resolve().parent
MATCHES_FILE    = ROOT / "matches_2026.csv"
LOCAL_DATA_FILE = ROOT / "data" / "quinela_data.json"

def get_secret(name: str, default: str = "") -> str:
    val = None
    try:
        val = st.secrets.get(name)
    except Exception:
        pass
    if val is None:
        val = os.environ.get(name, default)
    return str(val) if val is not None else default

def get_int_secret(name: str, default: int) -> int:
    try:
        return int(get_secret(name, str(default)))
    except Exception:
        return default

def get_bool_secret(name: str, default: bool) -> bool:
    raw = get_secret(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "si", "sí", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default

APP_TZ_NAME = get_secret("APP_TZ", "America/Mexico_City")
try:
    APP_TZ = ZoneInfo(APP_TZ_NAME)
except Exception:
    APP_TZ_NAME = "America/Mexico_City"
    APP_TZ      = ZoneInfo(APP_TZ_NAME)

ADMIN_PASSWORD      = get_secret("ADMIN_PASSWORD", "")
ADMIN_PASSWORD_HASH = get_secret("ADMIN_PASSWORD_HASH", "")
SUPABASE_URL        = get_secret("SUPABASE_URL", "")
SUPABASE_KEY        = get_secret("SUPABASE_SERVICE_ROLE_KEY", "") or get_secret("SUPABASE_KEY", "")
POINTS_EXACT        = max(1, get_int_secret("POINTS_EXACT", 3))
POINTS_RESULT       = max(0, get_int_secret("POINTS_RESULT", 1))
POINTS_SPECIAL      = max(0, get_int_secret("POINTS_SPECIAL", 5))
ENABLE_REGISTRATION = get_bool_secret("ENABLE_REGISTRATION", True)
USERNAME_RE         = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9_. -]{3,40}$")

# ──────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');

/* ── Design tokens ─────────────────────────────────────── */
:root {
  --verde:      #006341;
  --verde-osc:  #004d32;
  --verde-soft: #e9f5ef;
  --oro:        #c8962c;
  --oro-soft:   #fff4d6;
  --crema:      #f7f3ea;
  --tinta:      #15231d;
  --gris:       #66736d;
  --linea:      rgba(0,99,65,.14);
  --sombra:     0 14px 36px rgba(21,35,29,.10);
  --sombra-soft:0 8px 20px rgba(21,35,29,.08);
  --radius-sm:  12px;
  --radius-md:  18px;
  --radius-lg:  24px;
  --ease:       cubic-bezier(.4,0,.2,1);
  --dur:        180ms;
}

/* ── Dark-mode tokens ──────────────────────────────────── */
/* ── Keyframe animations ───────────────────────────────── */
@keyframes fadeUp {
  from { opacity:0; transform:translateY(14px); }
  to   { opacity:1; transform:translateY(0); }
}
@keyframes popIn {
  0%   { opacity:0; transform:scale(.88); }
  70%  { transform:scale(1.04); }
  100% { opacity:1; transform:scale(1); }
}
@keyframes shimmer {
  0%   { background-position: -400px 0; }
  100% { background-position:  400px 0; }
}
@keyframes pulseGlow {
  0%,100% { box-shadow: 0 0 0   0 rgba(200,150,44,.0); }
  50%      { box-shadow: 0 0 18px 4px rgba(200,150,44,.28); }
}

/* ── Base ──────────────────────────────────────────────── */
html, body, [class*="css"] { font-family:'IBM Plex Sans',sans-serif; }
h1, h2, h3 { font-family:'Bebas Neue',sans-serif; letter-spacing:1px; }

.stApp {
  background:
    radial-gradient(circle at top left, rgba(200,150,44,.14), transparent 32rem),
    linear-gradient(180deg, #fbfaf6 0%, #f6f1e8 48%, #ffffff 100%);
}
.block-container { padding-top:1.4rem; padding-bottom:3rem; max-width:1240px; }
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg,#ffffff 0%,#f7f3ea 100%);
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color:var(--tinta); }

/* ── Hero banner ───────────────────────────────────────── */
.hero-banner {
  position:relative; overflow:hidden;
  background:
    radial-gradient(circle at 88% 15%, rgba(200,150,44,.42), transparent 16rem),
    linear-gradient(135deg,#006341 0%,#004d32 46%,#141c18 100%);
  color:white; padding:28px 32px;
  border-radius:var(--radius-lg); margin-bottom:22px;
  border:1px solid rgba(255,255,255,.16); box-shadow:var(--sombra);
  animation: fadeUp var(--dur) var(--ease) both;
}
.hero-banner::before {
  content:""; position:absolute; inset:0;
  background: repeating-linear-gradient(
    -45deg,
    transparent 0, transparent 28px,
    rgba(255,255,255,.02) 28px, rgba(255,255,255,.02) 29px
  );
  pointer-events:none;
}
.hero-banner::after {
  content:""; position:absolute; inset:auto -60px -90px auto;
  width:240px; height:240px;
  border-radius:50%; border:28px solid rgba(255,255,255,.08);
}
.hero-kicker { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-bottom:12px; }
.hero-pill {
  display:inline-flex; align-items:center; gap:6px; padding:6px 11px; border-radius:999px;
  background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.20);
  color:white; font-size:.74rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
  transition: background var(--dur) var(--ease);
}
.hero-pill:hover { background:rgba(255,255,255,.22); }
.hero-title { font-family:'Bebas Neue'; font-size:3.25rem; line-height:.95; margin:0; color:white; }
.hero-subtitle { margin:10px 0 0; opacity:.90; max-width:760px; font-size:1.02rem; }

/* ── Section title ─────────────────────────────────────── */
.section-title { margin:4px 0 14px; animation: fadeUp var(--dur) var(--ease) both; }
.section-title h2, .section-title h3 { margin-bottom:2px; }
.section-title p { margin:0; color:var(--gris); }

/* ── Shared card base ──────────────────────────────────── */
.kpi-card, .podium-card, .empty-card, .quick-card {
  background:rgba(255,255,255,.88); border:1px solid var(--linea); border-radius:var(--radius-md);
  padding:16px 18px; box-shadow:var(--sombra-soft); height:100%;
  transition: box-shadow var(--dur) var(--ease), border-color var(--dur) var(--ease),
              transform var(--dur) var(--ease);
}

/* ── KPI card ──────────────────────────────────────────── */
.kpi-card {
  border-top:4px solid var(--verde);
  animation: fadeUp var(--dur) var(--ease) both;
}
.kpi-card:hover {
  border-color: var(--verde);
  box-shadow: 0 16px 36px rgba(21,35,29,.13);
  transform: translateY(-2px);
}
.kpi-card .kpi-top  { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.kpi-card .kpi-icon { font-size:1.4rem; }
.kpi-card .kpi-label{ color:var(--gris); font-size:.76rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }
.kpi-card .kpi-value{ font-family:'Bebas Neue'; color:var(--tinta); font-size:2.2rem; line-height:1; margin-top:4px; }
.kpi-card .kpi-hint { color:var(--gris); font-size:.82rem; margin-top:7px; }

/* ── Sidebar metric card ───────────────────────────────── */
.metric-card {
  background:linear-gradient(135deg,var(--verde),var(--verde-osc));
  color:white; padding:14px 18px; border-radius:16px;
  border-left:4px solid var(--oro); margin-bottom:10px;
  box-shadow:var(--sombra-soft);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.metric-card:hover { transform:translateX(3px); box-shadow:var(--sombra); }
.metric-card .label { font-size:.72rem; opacity:.82; text-transform:uppercase; letter-spacing:1px; }
.metric-card .value { font-family:'Bebas Neue'; font-size:1.9rem; color:var(--oro); line-height:1.1; }

/* ── Badges ────────────────────────────────────────────── */
.badge {
  display:inline-flex; align-items:center; color:white; font-size:.68rem; font-weight:800;
  padding:3px 9px; border-radius:999px; text-transform:uppercase;
  letter-spacing:.07em; white-space:nowrap; margin-right:5px;
  transition: filter var(--dur) var(--ease);
}
.badge:hover { filter: brightness(1.12); }
.b-group   { background:var(--verde); }
.b-open    { background:#2e7d32; }
.b-locked  { background:#b71c1c; }
.b-result  { background:#5d4037; }
.b-pending { background:#69756f; }

/* ── Podium ────────────────────────────────────────────── */
.podium-card {
  text-align:center; position:relative; overflow:hidden;
  animation: popIn 320ms var(--ease) both;
}
.podium-card.place-1 {
  border-top:5px solid var(--oro);
  background:linear-gradient(180deg,#fff9e8 0%,#ffffff 70%);
  animation-delay: 0ms;
  animation: pulseGlow 3s ease-in-out 1.2s 2, popIn 320ms var(--ease) both;
}
.podium-card.place-2 { border-top:5px solid #9aa4ad; animation-delay:80ms; }
.podium-card.place-3 { border-top:5px solid #b8743a; animation-delay:160ms; }
.podium-rank   { font-size:2rem; line-height:1; }
.podium-user   { font-weight:800; color:var(--tinta); margin-top:6px; min-height:28px; }
.podium-points { font-family:'Bebas Neue'; font-size:2.3rem; color:var(--verde); line-height:1; margin-top:6px; }
.podium-meta   { color:var(--gris); font-size:.82rem; margin-top:4px; }

/* ── Match card — FIX doble borde con st.container(border=True) ── */
/* Neutralizamos el borde nativo de Streamlit dentro del contexto de partidos */
[data-testid="stVerticalBlockBorderWrapper"] > [data-testid="stVerticalBlock"] {
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
}
.match-card {
  background:rgba(255,255,255,.96); border:1.5px solid rgba(0,99,65,.15);
  border-radius:var(--radius-md);
  padding:15px 16px; box-shadow:0 8px 22px rgba(21,35,29,.07); height:100%;
  transition: border-color var(--dur) var(--ease),
              box-shadow var(--dur) var(--ease),
              transform var(--dur) var(--ease);
}
.match-card:hover {
  border-color: rgba(200,150,44,.65);
  box-shadow: 0 16px 32px rgba(21,35,29,.14);
  transform: translateY(-2px);
}
.match-card .match-top   { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:10px; flex-wrap:wrap; }
.match-card .match-title { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:8px 0 4px; }
.team-name  { font-weight:800; color:var(--tinta); font-size:1.02rem; }
.vs-chip    { color:var(--gris); font-size:.75rem; font-weight:800; background:var(--verde-soft); padding:4px 7px; border-radius:999px; }
.match-meta { color:var(--gris); font-size:.82rem; margin-bottom:10px; }
.score-line { background:var(--verde-soft); border:1px solid rgba(0,99,65,.12); border-radius:var(--radius-sm); padding:9px 11px; margin:8px 0; }
.score-line.official { background:var(--oro-soft); border-color:rgba(200,150,44,.28); }
.score-title{ color:var(--gris); font-size:.72rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }
.score-value{ font-weight:800; color:var(--tinta); }

/* ── Empty state ───────────────────────────────────────── */
.empty-card { text-align:center; padding:30px 22px; }
.empty-card .empty-icon  { font-size:2.4rem; }
.empty-card .empty-title { font-weight:900; font-size:1.1rem; color:var(--tinta); margin-top:8px; }
.empty-card .empty-text  { color:var(--gris); max-width:620px; margin:6px auto 0; }

/* ── Quick-card / stage strip ──────────────────────────── */
.quick-card strong { color:var(--verde); }
.stage-strip { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin:12px 0 18px; }
.stage-mini {
  background:rgba(255,255,255,.90); border:1px solid var(--linea);
  border-radius:16px; padding:12px 14px; box-shadow:var(--sombra-soft);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.stage-mini:hover { transform:translateY(-2px); box-shadow:var(--sombra); }
.stage-mini .label { color:var(--gris); font-size:.72rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }
.stage-mini .value { font-family:'Bebas Neue'; font-size:1.8rem; line-height:1; color:var(--verde); margin-top:4px; }

/* ── Bracket card ──────────────────────────────────────── */
.bracket-card {
  background:rgba(255,255,255,.94); border:1px solid rgba(0,99,65,.14);
  border-radius:var(--radius-md); padding:14px 16px;
  box-shadow:var(--sombra-soft); height:100%;
  transition: border-color var(--dur) var(--ease),
              box-shadow var(--dur) var(--ease),
              transform var(--dur) var(--ease);
}
.bracket-card:hover {
  border-color:rgba(200,150,44,.5);
  box-shadow:0 12px 26px rgba(21,35,29,.12);
  transform:translateY(-2px);
}
.bracket-card .round { color:var(--oro); font-weight:900; font-size:.76rem; letter-spacing:.07em; text-transform:uppercase; }
.bracket-card .teams { font-weight:900; color:var(--tinta); margin:5px 0 6px; }
.bracket-card .meta  { color:var(--gris); font-size:.82rem; }

/* ── Tabs ──────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
  gap:4px; background:rgba(0,99,65,.08); border-radius:14px; padding:6px;
}
.stTabs [data-baseweb="tab"] {
  font-weight:800; border-radius:10px; padding:8px 13px;
  transition: background var(--dur) var(--ease), color var(--dur) var(--ease);
}
.stTabs [aria-selected="true"] { background:var(--verde)!important; color:white!important; }
details summary { font-weight:800; color:var(--verde); }
button[kind="primary"] { border-radius:999px!important; }

/* ── Award & special cards ─────────────────────────────── */
.award-card {
  background:linear-gradient(180deg,#ffffff 0%,#fbfaf6 100%);
  border:1px solid rgba(0,99,65,.14); border-radius:var(--radius-md);
  padding:16px 18px; box-shadow:var(--sombra-soft); height:100%;
  position:relative; overflow:hidden;
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.award-card:hover { transform:translateY(-2px); box-shadow:var(--sombra); }
.award-card::after {
  content:""; position:absolute; right:-28px; bottom:-34px;
  width:100px; height:100px; border-radius:50%; background:rgba(200,150,44,.12);
}
.award-card .award-icon   { font-size:1.8rem; line-height:1; }
.award-card .award-label  { color:var(--gris); font-size:.72rem; font-weight:900; letter-spacing:.07em; text-transform:uppercase; margin-top:8px; }
.award-card .award-winner { color:var(--tinta); font-weight:900; font-size:1.05rem; margin-top:4px; min-height:28px; }
.award-card .award-meta   { color:var(--verde); font-weight:800; font-size:.84rem; margin-top:3px; }

.special-card {
  background:rgba(255,255,255,.96); border:1px solid rgba(200,150,44,.26);
  border-radius:var(--radius-md);
  padding:14px 16px; box-shadow:0 8px 22px rgba(21,35,29,.07); height:100%;
  transition: border-color var(--dur) var(--ease), transform var(--dur) var(--ease);
}
.special-card:hover { border-color:rgba(200,150,44,.55); transform:translateY(-2px); }
.special-card .special-label  { color:var(--oro); font-weight:900; font-size:.76rem; letter-spacing:.07em; text-transform:uppercase; }
.special-card .special-help   { color:var(--gris); font-size:.82rem; margin:3px 0 8px; }
.special-card .special-result { background:var(--oro-soft); border:1px solid rgba(200,150,44,.25); border-radius:var(--radius-sm); padding:8px 10px; margin-top:8px; font-size:.88rem; }

/* ── Responsive / mobile ───────────────────────────────── */
@media (max-width: 760px) {
  .block-container  { padding-left:1rem; padding-right:1rem; }
  .hero-banner      { padding:18px 16px; border-radius:var(--radius-md); }
  .hero-title       { font-size:2.2rem; }
  .hero-subtitle    { font-size:.93rem; }
  .kpi-card .kpi-value { font-size:1.8rem; }
  .podium-points    { font-size:1.9rem; }
  .match-card .match-title { align-items:flex-start; flex-direction:column; gap:4px; }
  .stTabs [data-baseweb="tab"] { padding:6px 9px; font-size:.82rem; }
  .award-card, .special-card { border-radius:var(--radius-sm); }
}

/* ── Scrollbar styling (webkit) ────────────────────────── */
::-webkit-scrollbar       { width:6px; height:6px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:rgba(0,99,65,.3); border-radius:999px; }
::-webkit-scrollbar-thumb:hover { background:var(--verde); }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# SEGURIDAD
# ──────────────────────────────────────────────────────────────
def normalize_username(u: str) -> str:
    return " ".join(u.strip().split())

def user_key(u: str) -> str:
    return normalize_username(u).casefold()

def make_password_hash(pw: str, iters: int = 260_000) -> str:
    salt   = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iters)
    return f"pbkdf2_sha256${iters}${salt.hex()}${digest.hex()}"

def verify_password(pw: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, it_s, salt_hex, digest_hex = stored.split("$", 3)
            digest = hashlib.pbkdf2_hmac(
                "sha256", pw.encode(), bytes.fromhex(salt_hex), int(it_s)
            ).hex()
            return hmac.compare_digest(digest, digest_hex)
        except Exception:
            return False
    if re.fullmatch(r"[a-fA-F0-9]{64}", stored):
        return hmac.compare_digest(hashlib.sha256(pw.encode()).hexdigest(), stored)
    return False

def verify_admin(candidate: str) -> bool:
    if not candidate:
        return False
    if ADMIN_PASSWORD_HASH:
        return verify_password(candidate, ADMIN_PASSWORD_HASH)
    if ADMIN_PASSWORD:
        return hmac.compare_digest(candidate, ADMIN_PASSWORD)
    return False

# ──────────────────────────────────────────────────────────────
# STORE LOCAL
# ──────────────────────────────────────────────────────────────
class LocalStore:
    name = "JSON local"

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({
                "users": {}, "predictions": {}, "results": {}, "locks": {},
                "special_predictions": {}, "special_results": {}, "audit_log": []
            })
        self._migrate()

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "users": {}, "predictions": {}, "results": {}, "locks": {},
                "special_predictions": {}, "special_results": {}, "audit_log": []
            }

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="q_", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def _migrate(self) -> None:
        data    = self._load()
        changed = False

        def to_score(p: dict) -> dict:
            if "home_goals" in p:
                return p
            return {"home_goals": int(p.get("L", 0)), "away_goals": int(p.get("V", 0)),
                    "updated_at": p.get("updated_at")}

        if "usuarios" in data:
            for uname, pw_hash in data.pop("usuarios", {}).items():
                k = user_key(uname)
                data.setdefault("users", {})[k] = {
                    "username": normalize_username(uname),
                    "password_hash": pw_hash, "created_at": None,
                }
            changed = True
        if "pronosticos" in data:
            old = data.pop("pronosticos", {})
            data["predictions"] = {
                user_key(u): {mid: to_score(s) for mid, s in preds.items()}
                for u, preds in old.items()
            }
            changed = True
        if "resultados" in data:
            data["results"] = {mid: to_score(s) for mid, s in data.pop("resultados", {}).items()}
            changed = True
        for k in ("users", "predictions", "results", "locks", "special_predictions", "special_results"):
            data.setdefault(k, {})
        data.setdefault("audit_log", [])
        if changed:
            self._save(data)

    # ── Usuarios ─────────────────────────────────────────────
    def list_users(self) -> list[dict]:
        return list(self._load()["users"].values())

    def get_user(self, username: str) -> dict | None:
        return self._load()["users"].get(user_key(username))

    def create_user(self, username: str, pw_hash: str) -> None:
        data = self._load()
        k    = user_key(username)
        data["users"][k] = {
            "username":     normalize_username(username),
            "password_hash": pw_hash,
            "created_at":   datetime.now(APP_TZ).isoformat(timespec="seconds"),
        }
        data["predictions"].setdefault(k, {})
        self._save(data)

    def update_user_hash(self, username: str, pw_hash: str) -> None:
        data = self._load()
        k    = user_key(username)
        if k in data["users"]:
            data["users"][k]["password_hash"] = pw_hash
            self._save(data)

    # ── Pronósticos ──────────────────────────────────────────
    def get_predictions(self, username: str) -> dict:
        return self._load()["predictions"].get(user_key(username), {})

    def list_all_predictions(self) -> dict:
        return self._load()["predictions"]

    def upsert_prediction(self, username: str, match_id: str, home: int, away: int) -> None:
        data = self._load()
        k    = user_key(username)
        data["predictions"].setdefault(k, {})[match_id] = {
            "home_goals": int(home), "away_goals": int(away),
            "updated_at": datetime.now(APP_TZ).isoformat(timespec="seconds"),
        }
        self._save(data)

    # ── Resultados ───────────────────────────────────────────
    def list_results(self) -> dict:
        return self._load()["results"]

    def upsert_result(self, match_id: str, home: int, away: int) -> None:
        data = self._load()
        data["results"][match_id] = {
            "home_goals": int(home), "away_goals": int(away),
            "updated_at": datetime.now(APP_TZ).isoformat(timespec="seconds"),
        }
        self._save(data)

    def delete_result(self, match_id: str) -> None:
        data = self._load()
        data["results"].pop(match_id, None)
        self._save(data)

    # ── Bloqueos ─────────────────────────────────────────────
    def list_locks(self) -> dict:
        return self._load()["locks"]

    def set_lock(self, match_id: str, locked: bool) -> None:
        data = self._load()
        data["locks"][match_id] = bool(locked)
        self._save(data)

    # ── Resultado + bloqueo atómico ──────────────────────────
    def publish_result(self, match_id: str, home: int, away: int) -> tuple[bool, str]:
        try:
            data = self._load()
            data["results"][match_id] = {
                "home_goals": int(home), "away_goals": int(away),
                "updated_at": datetime.now(APP_TZ).isoformat(timespec="seconds"),
            }
            data["locks"][match_id] = True
            self._save(data)
            return True, "ok"
        except Exception as exc:
            return False, str(exc)

    # ── Pronósticos especiales / premios ─────────────────────
    def get_special_predictions(self, username: str) -> dict:
        return self._load().get("special_predictions", {}).get(user_key(username), {})

    def list_all_special_predictions(self) -> dict:
        return self._load().get("special_predictions", {})

    def upsert_special_prediction(self, username: str, category: str, value: str) -> None:
        data = self._load()
        k    = user_key(username)
        data.setdefault("special_predictions", {}).setdefault(k, {})[category] = {
            "category": category,
            "value": str(value).strip(),
            "updated_at": datetime.now(APP_TZ).isoformat(timespec="seconds"),
        }
        self._save(data)

    def list_special_results(self) -> dict:
        return self._load().get("special_results", {})

    def upsert_special_result(self, category: str, value: str, points: int) -> None:
        data = self._load()
        data.setdefault("special_results", {})[category] = {
            "category": category,
            "value": str(value).strip(),
            "points": int(points),
            "updated_at": datetime.now(APP_TZ).isoformat(timespec="seconds"),
        }
        self._save(data)

    def delete_special_result(self, category: str) -> None:
        data = self._load()
        data.setdefault("special_results", {}).pop(category, None)
        self._save(data)

    # ── Auditoría ────────────────────────────────────────────
    def append_audit(self, actor: str, event: str, detail: dict | None = None) -> None:
        try:
            data = self._load()
            data.setdefault("audit_log", []).append({
                "id":         len(data["audit_log"]) + 1,
                "created_at": datetime.now(APP_TZ).isoformat(timespec="seconds"),
                "actor":      str(actor or "system"),
                "event":      str(event),
                "detail":     detail or {},
            })
            self._save(data)
        except Exception:
            pass

    def list_audit(self, limit: int = 100) -> list[dict]:
        rows = self._load().get("audit_log", [])
        return list(reversed(rows))[:limit]

    def export_all(self) -> dict:
        return self._load()


# ──────────────────────────────────────────────────────────────
# STORE SUPABASE
# ──────────────────────────────────────────────────────────────
class SupabaseStore:
    name = "Supabase"

    def __init__(self, url: str, key: str):
        if _sb_create is None:
            raise RuntimeError("supabase no instalado. pip install supabase")
        self.client = _sb_create(url, key)

    def list_users(self) -> list[dict]:
        return (self.client.table("quinela_users")
                .select("username,display_name,password_hash,created_at").execute().data or [])

    def get_user(self, username: str) -> dict | None:
        rows = (self.client.table("quinela_users")
                .select("username,display_name,password_hash,created_at")
                .eq("username", user_key(username)).limit(1).execute().data or [])
        return rows[0] if rows else None

    def create_user(self, username: str, pw_hash: str) -> None:
        self.client.table("quinela_users").insert({
            "username":     user_key(username),
            "display_name": normalize_username(username),
            "password_hash": pw_hash,
        }).execute()

    def update_user_hash(self, username: str, pw_hash: str) -> None:
        self.client.table("quinela_users").update({"password_hash": pw_hash}).eq(
            "username", user_key(username)).execute()

    def get_predictions(self, username: str) -> dict:
        rows = (self.client.table("quinela_predictions")
                .select("match_id,home_goals,away_goals,updated_at")
                .eq("username", user_key(username)).execute().data or [])
        return {r["match_id"]: r for r in rows}

    def list_all_predictions(self) -> dict:
        rows = (self.client.table("quinela_predictions")
                .select("username,match_id,home_goals,away_goals,updated_at").execute().data or [])
        out: dict = {}
        for r in rows:
            out.setdefault(r["username"], {})[r["match_id"]] = r
        return out

    def upsert_prediction(self, username: str, match_id: str, home: int, away: int) -> None:
        self.client.table("quinela_predictions").upsert({
            "username":   user_key(username), "match_id": match_id,
            "home_goals": int(home), "away_goals": int(away),
            "updated_at": datetime.now(APP_TZ).isoformat(),
        }, on_conflict="username,match_id").execute()

    def list_results(self) -> dict:
        rows = (self.client.table("quinela_results")
                .select("match_id,home_goals,away_goals,updated_at").execute().data or [])
        return {r["match_id"]: r for r in rows}

    def upsert_result(self, match_id: str, home: int, away: int) -> None:
        self.client.table("quinela_results").upsert({
            "match_id":   match_id,
            "home_goals": int(home), "away_goals": int(away),
            "updated_at": datetime.now(APP_TZ).isoformat(),
        }, on_conflict="match_id").execute()

    def delete_result(self, match_id: str) -> None:
        self.client.table("quinela_results").delete().eq("match_id", match_id).execute()

    def list_locks(self) -> dict:
        rows = (self.client.table("quinela_locks")
                .select("match_id,locked").execute().data or [])
        return {r["match_id"]: bool(r.get("locked")) for r in rows}

    def set_lock(self, match_id: str, locked: bool) -> None:
        self.client.table("quinela_locks").upsert({
            "match_id": match_id, "locked": bool(locked),
            "updated_at": datetime.now(APP_TZ).isoformat(),
        }, on_conflict="match_id").execute()

    def publish_result(self, match_id: str, home: int, away: int) -> tuple[bool, str]:
        try:
            self.upsert_result(match_id, home, away)
        except Exception as exc:
            return False, f"Error al guardar resultado: {exc}"
        try:
            self.set_lock(match_id, True)
        except Exception as exc:
            return False, (
                f"Resultado guardado ✓, pero el bloqueo falló: {exc}\n"
                "Activa el bloqueo manualmente en el panel de Bloqueos."
            )
        return True, "ok"

    # ── Pronósticos especiales / premios ─────────────────────
    def get_special_predictions(self, username: str) -> dict:
        try:
            rows = (self.client.table("quinela_special_predictions")
                    .select("category,value,updated_at")
                    .eq("username", user_key(username)).execute().data or [])
            return {r["category"]: r for r in rows}
        except Exception:
            return {}

    def list_all_special_predictions(self) -> dict:
        try:
            rows = (self.client.table("quinela_special_predictions")
                    .select("username,category,value,updated_at").execute().data or [])
        except Exception:
            return {}
        out: dict = {}
        for r in rows:
            out.setdefault(r["username"], {})[r["category"]] = r
        return out

    def upsert_special_prediction(self, username: str, category: str, value: str) -> None:
        self.client.table("quinela_special_predictions").upsert({
            "username": user_key(username),
            "category": category,
            "value": str(value).strip(),
            "updated_at": datetime.now(APP_TZ).isoformat(),
        }, on_conflict="username,category").execute()

    def list_special_results(self) -> dict:
        try:
            rows = (self.client.table("quinela_special_results")
                    .select("category,value,points,updated_at").execute().data or [])
            return {r["category"]: r for r in rows}
        except Exception:
            return {}

    def upsert_special_result(self, category: str, value: str, points: int) -> None:
        self.client.table("quinela_special_results").upsert({
            "category": category,
            "value": str(value).strip(),
            "points": int(points),
            "updated_at": datetime.now(APP_TZ).isoformat(),
        }, on_conflict="category").execute()

    def delete_special_result(self, category: str) -> None:
        self.client.table("quinela_special_results").delete().eq("category", category).execute()

    def append_audit(self, actor: str, event: str, detail: dict | None = None) -> None:
        try:
            self.client.table("quinela_audit_log").insert({
                "actor": str(actor or "system"),
                "event": str(event),
                "detail": detail or {},
            }).execute()
        except Exception:
            pass

    def list_audit(self, limit: int = 100) -> list[dict]:
        try:
            return (self.client.table("quinela_audit_log")
                    .select("created_at,actor,event,detail")
                    .order("created_at", desc=True)
                    .limit(limit).execute().data or [])
        except Exception:
            return []

    def export_all(self) -> dict:
        return {
            "users":       self.list_users(),
            "predictions": self.list_all_predictions(),
            "results":     self.list_results(),
            "locks":       self.list_locks(),
            "special_predictions": self.list_all_special_predictions(),
            "special_results": self.list_special_results(),
            "audit_log":   self.list_audit(500),
            "exported_at": datetime.now(APP_TZ).isoformat(),
        }


# ──────────────────────────────────────────────────────────────
# STORE FACTORY — sin @cache_resource para no atrapar errores
# ──────────────────────────────────────────────────────────────
def _build_store():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            return SupabaseStore(SUPABASE_URL, SUPABASE_KEY)
        except Exception as exc:
            st.sidebar.warning(f"Supabase no disponible ({exc}). Usando almacenamiento local.")
    return LocalStore(LOCAL_DATA_FILE)

if "store" not in st.session_state:
    st.session_state.store = _build_store()

STORE: LocalStore | SupabaseStore = st.session_state.store

# ──────────────────────────────────────────────────────────────
# CACHE DE DATOS VIVOS — TTL 15s para reducir lecturas
# ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=15, show_spinner=False)
def _cached_users():         return STORE.list_users()
@st.cache_data(ttl=15, show_spinner=False)
def _cached_all_preds():     return STORE.list_all_predictions()
@st.cache_data(ttl=15, show_spinner=False)
def _cached_results():       return STORE.list_results()
@st.cache_data(ttl=15, show_spinner=False)
def _cached_locks():         return STORE.list_locks()
@st.cache_data(ttl=15, show_spinner=False)
def _cached_special_preds(): return STORE.list_all_special_predictions()
@st.cache_data(ttl=15, show_spinner=False)
def _cached_special_results(): return STORE.list_special_results()

def get_live_data():
    """Una sola función de entrada para todos los datos vivos."""
    return (
        _cached_users(),
        _cached_all_preds(),
        _cached_results(),
        _cached_locks(),
        _cached_special_preds(),
        _cached_special_results(),
    )

def invalidate_cache():
    """Llama después de cualquier escritura para que la UI refleje el cambio."""
    _cached_users.clear()
    _cached_all_preds.clear()
    _cached_results.clear()
    _cached_locks.clear()
    _cached_special_preds.clear()
    _cached_special_results.clear()

# ──────────────────────────────────────────────────────────────
# CALENDARIO
# ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_matches() -> pd.DataFrame:
    required = {"match_id", "group", "home", "away", "match_date", "venue", "kickoff_at"}
    if not MATCHES_FILE.exists():
        st.error("No existe matches_2026.csv.")
        return pd.DataFrame()
    df = pd.read_csv(MATCHES_FILE).fillna("")
    missing = required - set(df.columns)
    if missing:
        st.error(f"matches_2026.csv faltan columnas: {', '.join(sorted(missing))}")
        return pd.DataFrame()
    df["match_id"] = df["match_id"].astype(str)
    df["group"]    = df["group"].astype(str)
    return df

@st.cache_data(show_spinner=False)
def validate_matches(df: pd.DataFrame) -> list[str]:
    warnings: list[str] = []
    if df.empty:
        return ["Calendario vacío o no cargado."]
    dup = df[df["match_id"].duplicated()]["match_id"].tolist()
    if dup:
        warnings.append(f"IDs duplicados: {', '.join(map(str, dup))}")
    empty_ko = int((df["kickoff_at"].astype(str).str.strip() == "").sum())
    if empty_ko:
        warnings.append(f"{empty_ko} partidos sin kickoff_at — requerirán bloqueo manual.")
    for r in df.itertuples(index=False):
        raw = str(getattr(r, "kickoff_at", "")).strip()
        if raw:
            try:
                datetime.fromisoformat(raw)
            except Exception:
                warnings.append(f"kickoff_at inválido en {r.match_id}: {raw}")
    return warnings

MATCHES          = load_matches()
RAW_BUCKETS       = sorted(MATCHES["group"].dropna().unique().tolist()) if not MATCHES.empty else []
GROUP_ORDER       = list("ABCDEFGHIJKL")
ROUND_ORDER       = ["16avos", "Octavos", "Cuartos", "Semifinales", "Tercer lugar", "Final"]
GROUPS            = [g for g in GROUP_ORDER if g in RAW_BUCKETS]
KNOCKOUT_ROUNDS   = [r for r in ROUND_ORDER if r in RAW_BUCKETS]
BUCKETS           = GROUPS + KNOCKOUT_ROUNDS
MATCH_IDX         = {r.match_id: r for r in MATCHES.itertuples(index=False)} if not MATCHES.empty else {}
CALENDAR_WARNINGS = validate_matches(MATCHES)
TOTAL_MATCHES     = len(MATCHES)
GROUP_MATCHES     = int(MATCHES["group"].isin(GROUPS).sum()) if not MATCHES.empty else 0
KNOCKOUT_MATCHES  = int(MATCHES["group"].isin(KNOCKOUT_ROUNDS).sum()) if not MATCHES.empty else 0

# ──────────────────────────────────────────────────────────────
# ETAPAS / RONDAS
# ──────────────────────────────────────────────────────────────
def is_group_bucket(bucket: str) -> bool:
    return str(bucket) in GROUPS

def is_group_stage(row: Any) -> bool:
    return is_group_bucket(getattr(row, "group", ""))

def is_knockout_stage(row: Any) -> bool:
    return str(getattr(row, "group", "")) in KNOCKOUT_ROUNDS

def stage_label_from_bucket(bucket: str) -> str:
    return "Fase de grupos" if is_group_bucket(bucket) else "Eliminatorias"

def bucket_label_from_value(bucket: str) -> str:
    return f"Grupo {bucket}" if is_group_bucket(bucket) else str(bucket)

def bucket_label(row: Any) -> str:
    return bucket_label_from_value(str(getattr(row, "group", "")))

def bucket_format(bucket: str) -> str:
    if bucket == "Todos":
        return "Todos"
    return bucket_label_from_value(bucket)

def match_title(row: Any) -> str:
    return f"{getattr(row, 'home', '')} vs {getattr(row, 'away', '')}"

# ──────────────────────────────────────────────────────────────
# LÓGICA DE JUEGO
# ──────────────────────────────────────────────────────────────
def parse_kickoff(value: str) -> datetime | None:
    if not value or str(value).strip() == "":
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=APP_TZ)
        return dt.astimezone(APP_TZ)
    except Exception:
        return None

def is_locked(row: Any, locks: dict, results: dict) -> bool:
    if row.match_id in results:
        return True
    if locks.get(row.match_id, False):
        return True
    ko = parse_kickoff(getattr(row, "kickoff_at", ""))
    return bool(ko and datetime.now(APP_TZ) >= ko)

def fmt_kickoff(row: Any) -> str:
    ko = parse_kickoff(getattr(row, "kickoff_at", ""))
    if ko:
        return ko.strftime("%d %b %Y · %H:%M (CDMX)")
    return f"{getattr(row, 'match_date', '')} · hora por confirmar"

def calc_pts(ph: int, pa: int, rh: int, ra: int) -> int:
    if ph == rh and pa == ra:
        return POINTS_EXACT
    return POINTS_RESULT if ((ph > pa) - (ph < pa)) == ((rh > ra) - (rh < ra)) else 0

def pts_label(pts: int) -> str:
    if pts == POINTS_EXACT:
        return f"🎯 Exacto · +{POINTS_EXACT}"
    if pts == POINTS_RESULT and POINTS_RESULT > 0:
        return f"✅ Resultado · +{POINTS_RESULT}"
    return "❌ Sin puntos"

def build_standings(users, all_preds, results) -> pd.DataFrame:
    rows = []
    for u in users:
        ukey    = user_key(u["username"])
        display = u.get("display_name") or u["username"]
        preds   = all_preds.get(ukey, {})
        pts = exactos = correctos = evaluados = pronosticados = dif = 0
        for mid, pred in preds.items():
            pronosticados += 1
            res = results.get(mid)
            if not res:
                continue
            evaluados += 1
            ph, pa = int(pred["home_goals"]), int(pred["away_goals"])
            rh, ra = int(res["home_goals"]),  int(res["away_goals"])
            p       = calc_pts(ph, pa, rh, ra)
            pts      += p
            exactos  += int(p == POINTS_EXACT)
            correctos += int(p >= POINTS_RESULT and POINTS_RESULT > 0)
            dif       += abs(ph - rh) + abs(pa - ra)
        rows.append({
            "_ukey":         ukey,           # columna interna, se oculta en UI
            "Usuario":       display,
            "Puntos":        pts,
            "Exactos 🎯":   exactos,
            "Acertados ✅":  correctos,
            "Dif. marcador": dif,
            "Evaluados":     evaluados,
            "Pronosticados": pronosticados,
            "Promedio":      round(pts / evaluados, 2) if evaluados else 0.0,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(
        ["Puntos", "Exactos 🎯", "Acertados ✅", "Dif. marcador", "Pronosticados"],
        ascending=[False, False, False, True, False],
    ).reset_index(drop=True)

def build_predictions_export(users, all_preds, results) -> pd.DataFrame:
    name_by_key = {user_key(u["username"]): (u.get("display_name") or u["username"]) for u in users}
    rows = []
    for ukey, preds in all_preds.items():
        for mid, pred in preds.items():
            match      = MATCH_IDX.get(mid)
            res        = results.get(mid)
            ph, pa     = int(pred["home_goals"]), int(pred["away_goals"])
            pts_val    = ""
            result_txt = ""
            if res:
                rh, ra     = int(res["home_goals"]), int(res["away_goals"])
                pts_val    = calc_pts(ph, pa, rh, ra)
                result_txt = f"{rh}-{ra}"
            rows.append({
                "usuario":    name_by_key.get(ukey, ukey),
                "match_id":   mid,
                "etapa":      stage_label_from_bucket(str(getattr(match, "group", ""))) if match else "",
                "grupo_ronda": bucket_label_from_value(str(getattr(match, "group", ""))) if match else "",
                "partido":    f"{getattr(match, 'home', '')} vs {getattr(match, 'away', '')}",
                "pronostico": f"{ph}-{pa}",
                "resultado":  result_txt,
                "puntos":     pts_val,
                "actualizado": pred.get("updated_at", ""),
            })
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────
# TABLAS POR ETAPA Y PREMIOS v9
# ──────────────────────────────────────────────────────────────
SPECIAL_CATEGORIES = [
    {"key": "campeon", "label": "Campeón", "icon": "🏆", "kind": "team", "help": "Equipo que levantará la Copa del Mundo."},
    {"key": "subcampeon", "label": "Subcampeón", "icon": "🥈", "kind": "team", "help": "Equipo que perderá la final."},
    {"key": "tercer_lugar", "label": "Tercer lugar", "icon": "🥉", "kind": "team", "help": "Ganador del partido por tercer lugar."},
    {"key": "balon_oro", "label": "Balón de Oro", "icon": "🟡", "kind": "player", "help": "Mejor jugador del torneo."},
    {"key": "bota_oro", "label": "Bota de Oro", "icon": "👟", "kind": "player", "help": "Máximo goleador del torneo."},
    {"key": "guante_oro", "label": "Guante de Oro", "icon": "🧤", "kind": "player", "help": "Mejor portero del torneo."},
    {"key": "mejor_joven", "label": "Mejor jugador joven", "icon": "🌟", "kind": "player", "help": "Jugador joven más destacado."},
    {"key": "fair_play", "label": "Premio Fair Play", "icon": "🤝", "kind": "team", "help": "Selección con mejor juego limpio."},
    {"key": "caballo_negro", "label": "Caballo negro", "icon": "🐎", "kind": "team", "help": "Selección revelación o sorpresa del torneo."},
]
SPECIAL_LABELS = {c["key"]: c["label"] for c in SPECIAL_CATEGORIES}


def _norm_answer(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _team_options() -> list[str]:
    teams = set()
    for r in MATCHES.itertuples(index=False):
        for name in [str(r.home), str(r.away)]:
            low = name.casefold()
            if name and "ganador" not in low and "perdedor" not in low and "grupo" not in low:
                teams.add(name)
    return sorted(teams)


def match_ids_for_stage(stage: str) -> set[str]:
    if stage == "grupos":
        buckets = set(GROUPS)
    elif stage == "eliminatorias":
        buckets = set(KNOCKOUT_ROUNDS)
    else:
        buckets = set(GROUPS + KNOCKOUT_ROUNDS)
    return {r.match_id for r in MATCHES.itertuples(index=False) if r.group in buckets}


def build_stage_standings(users, all_preds, results, stage: str, include_specials: bool = False,
                          all_special_preds: dict | None = None, special_results: dict | None = None) -> pd.DataFrame:
    mids = match_ids_for_stage(stage)
    rows = []
    for u in users:
        ukey    = user_key(u["username"])
        display = u.get("display_name") or u["username"]
        preds   = all_preds.get(ukey, {})
        pts = exactos = correctos = evaluados = pronosticados = dif = 0
        for mid, pred in preds.items():
            if mid not in mids:
                continue
            pronosticados += 1
            res = results.get(mid)
            if not res:
                continue
            evaluados += 1
            ph, pa = int(pred["home_goals"]), int(pred["away_goals"])
            rh, ra = int(res["home_goals"]), int(res["away_goals"])
            p       = calc_pts(ph, pa, rh, ra)
            pts      += p
            exactos  += int(p == POINTS_EXACT)
            correctos += int(p >= POINTS_RESULT and POINTS_RESULT > 0)
            dif       += abs(ph - rh) + abs(pa - ra)

        special_pts = special_hits = special_done = 0
        if include_specials:
            spreds = (all_special_preds or {}).get(ukey, {})
            sres   = special_results or {}
            for cat, official in sres.items():
                if not official.get("value"):
                    continue
                pred = spreds.get(cat, {})
                if not pred or not pred.get("value"):
                    continue
                special_done += 1
                if _norm_answer(pred.get("value")) == _norm_answer(official.get("value")):
                    special_hits += 1
                    special_pts += int(official.get("points", POINTS_SPECIAL) or 0)

        total_pts = pts + special_pts
        rows.append({
            "_ukey": ukey,
            "Usuario": display,
            "Puntos": total_pts,
            "Puntos partidos": pts,
            "Bonus premios": special_pts,
            "Exactos 🎯": exactos,
            "Acertados ✅": correctos,
            "Premios 🏅": special_hits,
            "Dif. marcador": dif,
            "Evaluados": evaluados,
            "Pronosticados": pronosticados,
            "Promedio": round(pts / evaluados, 2) if evaluados else 0.0,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(
        ["Puntos", "Exactos 🎯", "Acertados ✅", "Premios 🏅", "Dif. marcador", "Pronosticados"],
        ascending=[False, False, False, False, True, False],
    ).reset_index(drop=True)


def build_global_standings_with_specials(users, all_preds, results, all_special_preds, special_results) -> pd.DataFrame:
    base = build_stage_standings(users, all_preds, results, "global", include_specials=True,
                                 all_special_preds=all_special_preds, special_results=special_results)
    return base


def stage_display_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    out = df.drop(columns=["_ukey"], errors="ignore").copy()
    out.insert(0, "Pos.", [f"{medals.get(i+1, '')} {i+1}" for i in range(len(out))])
    return out


def group_award_rows(group_df: pd.DataFrame) -> list[dict]:
    if group_df.empty:
        return []

    def winners(metric: str, mode: str = "max", denom: str | None = None, min_eval: int = 1) -> tuple[str, str]:
        df = group_df.copy()
        if min_eval:
            df = df[df["Evaluados"] >= min_eval]
        if df.empty:
            return "—", "Sin partidos evaluados"
        if denom:
            vals = df[metric] / df[denom].replace(0, pd.NA)
            df = df.assign(_metric=vals.fillna(0))
            metric_col = "_metric"
        else:
            metric_col = metric
        best = df[metric_col].max() if mode == "max" else df[metric_col].min()
        tie = df[df[metric_col] == best]
        names = ", ".join(tie["Usuario"].astype(str).head(3).tolist())
        if len(tie) > 3:
            names += f" +{len(tie)-3}"
        if denom:
            meta = f"{best:.0%}" if best <= 1 else f"{best:.2f}"
        else:
            meta = f"{int(best)}" if float(best).is_integer() else f"{best:.2f}"
        return names, meta

    exact_names, exact_meta = winners("Exactos 🎯")
    acc_names, acc_meta = winners("Acertados ✅")
    eff_names, eff_meta = winners("Puntos partidos", denom="Evaluados")
    dif_names, dif_meta = winners("Dif. marcador", mode="min")
    part_names, part_meta = winners("Pronosticados")
    avg_names, avg_meta = winners("Promedio")
    return [
        {"icon": "🎯", "label": "Más marcadores exactos", "winner": exact_names, "meta": f"{exact_meta} exactos"},
        {"icon": "✅", "label": "Más resultados acertados", "winner": acc_names, "meta": f"{acc_meta} aciertos"},
        {"icon": "📈", "label": "Mayor efectividad", "winner": eff_names, "meta": f"{eff_meta} puntos por partido evaluado"},
        {"icon": "🧮", "label": "Mejor diferencia acumulada", "winner": dif_names, "meta": f"{dif_meta} goles de diferencia"},
        {"icon": "📝", "label": "Mayor participación", "winner": part_names, "meta": f"{part_meta} pronósticos"},
        {"icon": "🔥", "label": "Mejor promedio", "winner": avg_names, "meta": f"{avg_meta} pts/partido"},
    ]


def special_predictions_export(users, all_special_preds, special_results) -> pd.DataFrame:
    name_by_key = {user_key(u["username"]): (u.get("display_name") or u["username"]) for u in users}
    rows = []
    for ukey, preds in (all_special_preds or {}).items():
        for cat, pred in preds.items():
            official = (special_results or {}).get(cat, {})
            ok = ""
            pts = ""
            if official.get("value") and pred.get("value"):
                is_hit = _norm_answer(pred.get("value")) == _norm_answer(official.get("value"))
                ok = "Sí" if is_hit else "No"
                pts = int(official.get("points", POINTS_SPECIAL) or 0) if is_hit else 0
            rows.append({
                "usuario": name_by_key.get(ukey, ukey),
                "categoria": SPECIAL_LABELS.get(cat, cat),
                "pronostico": pred.get("value", ""),
                "oficial": official.get("value", ""),
                "acierto": ok,
                "puntos": pts,
                "actualizado": pred.get("updated_at", ""),
            })
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────
# COMPONENTES VISUALES v8
# ──────────────────────────────────────────────────────────────
def pct_txt(num: int, den: int) -> str:
    if den <= 0:
        return "0%"
    return f"{round((num / den) * 100):.0f}%"

def render_kpi(container, label: str, value: str | int, hint: str = "", icon: str = ""):
    with container:
        st.markdown(f"""
        <div class="kpi-card">
          <div class="kpi-top">
            <div>
              <div class="kpi-label">{label}</div>
              <div class="kpi-value">{value}</div>
            </div>
            <div class="kpi-icon">{icon}</div>
          </div>
          <div class="kpi-hint">{hint}</div>
        </div>
        """, unsafe_allow_html=True)

def render_empty_state(icon: str, title: str, text: str):
    st.markdown(f"""
    <div class="empty-card">
      <div class="empty-icon">{icon}</div>
      <div class="empty-title">{title}</div>
      <div class="empty-text">{text}</div>
    </div>
    """, unsafe_allow_html=True)

def render_section_title(title: str, subtitle: str = ""):
    st.markdown(f"""
    <div class="section-title">
      <h2>{title}</h2>
      <p>{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)

def render_award_card(container, icon: str, label: str, winner: str, meta: str):
    with container:
        st.markdown(f"""
        <div class="award-card">
          <div class="award-icon">{icon}</div>
          <div class="award-label">{label}</div>
          <div class="award-winner">{winner}</div>
          <div class="award-meta">{meta}</div>
        </div>
        """, unsafe_allow_html=True)


def render_stage_table(title: str, subtitle: str, df: pd.DataFrame, filename: str):
    render_section_title(title, subtitle)
    if df.empty:
        render_empty_state("🏆", "Sin tabla disponible", "Aún no hay participantes o resultados suficientes para esta etapa.")
        return
    render_podium(df)
    st.write("")
    display_df = stage_display_df(df)
    max_pts = int(display_df["Puntos"].max()) or 1
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Puntos": st.column_config.ProgressColumn("Puntos", max_value=max_pts, format="%d"),
            "Promedio": st.column_config.NumberColumn(format="%.2f"),
            "Pos.": st.column_config.TextColumn(width="small"),
            "Bonus premios": st.column_config.NumberColumn(width="small"),
            "Premios 🏅": st.column_config.NumberColumn(width="small"),
        },
    )
    st.download_button(
        "⬇️ Descargar CSV",
        data=display_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        use_container_width=True,
        key=f"download_stage_{filename}",
    )


# FIX: podio dinámico — muestra min(3, len(standings)) lugares reales
def render_podium(standings: pd.DataFrame):
    if standings.empty:
        return
    medals = ["🥇", "🥈", "🥉"]
    n      = min(3, len(standings))
    cols   = st.columns(3)
    for i in range(3):
        with cols[i]:
            if i < n:
                r = standings.iloc[i]
                st.markdown(f"""
                <div class="podium-card place-{i+1}">
                  <div class="podium-rank">{medals[i]}</div>
                  <div class="podium-user">{r['Usuario']}</div>
                  <div class="podium-points">{int(r['Puntos'])}</div>
                  <div class="podium-meta">{int(r['Exactos 🎯'])} exactos · {int(r['Acertados ✅'])} aciertos</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="podium-card place-{i+1}">
                  <div class="podium-rank">{medals[i]}</div>
                  <div class="podium-user" style="opacity:.45">Lugar disponible</div>
                  <div class="podium-points" style="opacity:.3">—</div>
                  <div class="podium-meta">Aún no hay suficientes participantes</div>
                </div>
                """, unsafe_allow_html=True)

# FIX: recibe my_preds como parámetro en lugar de capturarlo por closure
def group_progress_df(my_preds: dict) -> pd.DataFrame:
    rows = []
    for g in GROUPS:
        ids   = [r.match_id for r in MATCHES.itertuples(index=False) if r.group == g]
        done  = sum(1 for mid in ids if mid in my_preds)
        total = len(ids)
        rows.append({
            "Grupo":         g,
            "Pronosticados": done,
            "Total":         total,
            "Avance":        round((done / total) * 100) if total else 0,
        })
    return pd.DataFrame(rows)

def stage_progress_df(my_preds: dict) -> pd.DataFrame:
    specs = [("Fase de grupos", GROUPS), ("Eliminatorias", KNOCKOUT_ROUNDS)]
    rows = []
    for stage, buckets in specs:
        ids = [r.match_id for r in MATCHES.itertuples(index=False) if r.group in buckets]
        done = sum(1 for mid in ids if mid in my_preds)
        total = len(ids)
        rows.append({
            "Etapa": stage,
            "Pronosticados": done,
            "Total": total,
            "Avance": round((done / total) * 100) if total else 0,
        })
    return pd.DataFrame(rows)

def match_state(row: Any, locks: dict, results: dict) -> tuple[str, str]:
    result = results.get(row.match_id)
    locked = is_locked(row, locks, results)
    if result:
        return "b-result", "Resultado"
    if locked:
        return "b-locked", "Bloqueado"
    return "b-open", "Abierto"

# FIX: render_match_header ahora recibe locks/results explícitamente y SÍ se usa en los tabs
def render_match_card_header(row: Any, locks: dict, results: dict):
    b_status, b_text = match_state(row, locks, results)
    bucket_text = bucket_label(row)
    stage_text  = stage_label_from_bucket(str(row.group))
    st.markdown(f"""
    <div class="match-top">
      <div>
        <span class="badge b-group">{bucket_text}</span>
        <span class="badge {b_status}">{b_text}</span>
      </div>
      <span class="badge b-pending">{row.match_id}</span>
    </div>
    <div class="match-title">
      <span class="team-name">{row.home}</span>
      <span class="vs-chip">VS</span>
      <span class="team-name">{row.away}</span>
    </div>
    <div class="match-meta">🏁 {stage_text} · 📅 {fmt_kickoff(row)} · 📍 {row.venue}</div>
    """, unsafe_allow_html=True)

# FIX: gráfica Top-10 con colores IMP usando plotly (no st.bar_chart)
def render_top10_chart(standings: pd.DataFrame):
    try:
        import plotly.graph_objects as go  # type: ignore
        top = standings.head(10)
        colors = [
            "#c8962c" if i == 0 else "#9aa4ad" if i == 1 else "#b8743a" if i == 2
            else "#006341"
            for i in range(len(top))
        ]
        fig = go.Figure(go.Bar(
            x=top["Usuario"].tolist(),
            y=top["Puntos"].tolist(),
            marker_color=colors,
            text=top["Puntos"].tolist(),
            textposition="outside",
        ))
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="IBM Plex Sans", color="#15231d"),
            margin=dict(t=20, b=10, l=0, r=0),
            xaxis=dict(title="", tickfont=dict(size=12)),
            yaxis=dict(title="Puntos", gridcolor="rgba(0,99,65,.1)"),
            showlegend=False,
            height=320,
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        # Fallback si plotly no está instalado
        chart_df = standings.head(10).set_index("Usuario")[["Puntos"]]
        st.bar_chart(chart_df, use_container_width=True)

# NUEVO: countdown al próximo partido desbloqueado
def render_countdown():
    now = datetime.now(APP_TZ)
    upcoming = []
    for row in MATCHES.itertuples(index=False):
        if row.match_id in RESULTS:
            continue
        ko = parse_kickoff(getattr(row, "kickoff_at", ""))
        if ko and ko > now:
            upcoming.append((ko, row))
    if not upcoming:
        return
    upcoming.sort(key=lambda x: x[0])
    ko, row = upcoming[0]
    delta   = ko - now
    hrs, rem = divmod(int(delta.total_seconds()), 3600)
    mins     = rem // 60
    if hrs > 72:
        txt = f"en {hrs // 24} días"
    elif hrs > 0:
        txt = f"en {hrs}h {mins}m"
    else:
        txt = f"en {mins} min"
    st.markdown(f"""
    <div style="background:linear-gradient(90deg,var(--verde-soft),var(--oro-soft));
         border:1px solid rgba(200,150,44,.3); border-radius:14px;
         padding:12px 18px; margin-bottom:14px; display:flex;
         align-items:center; gap:14px; flex-wrap:wrap;">
      <span style="font-size:1.5rem">⏱️</span>
      <div>
        <div style="font-size:.74rem;font-weight:800;text-transform:uppercase;
             letter-spacing:.07em;color:var(--gris)">Próximo partido</div>
        <div style="font-weight:800;color:var(--tinta)">
          {row.home} vs {row.away} — {bucket_label(row)}
        </div>
        <div style="font-size:.88rem;color:var(--verde);font-weight:700">
          {ko.strftime('%d %b · %H:%M CDMX')} · <strong>{txt}</strong>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# NUEVO: avatar/inicial del usuario para el sidebar
def render_user_avatar(username: str, pts: int, pos: int | str):
    initial = username[0].upper() if username else "?"
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:12px;
         background:linear-gradient(135deg,var(--verde),var(--verde-osc));
         border-radius:16px; padding:14px 16px; margin-bottom:12px;
         border-left:4px solid var(--oro); box-shadow:var(--sombra-soft);">
      <div style="width:44px;height:44px;border-radius:50%;
           background:var(--oro);display:flex;align-items:center;
           justify-content:center;font-family:'Bebas Neue';
           font-size:1.4rem;color:var(--tinta);flex-shrink:0;">{initial}</div>
      <div>
        <div style="font-weight:800;color:white;font-size:.95rem;
             line-height:1.2;">{username}</div>
        <div style="color:var(--oro);font-size:.82rem;font-weight:700;margin-top:2px;">
          #{pos} · {pts} pts
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# NUEVO: heat map de cobertura de pronósticos por partido (admin)
def render_coverage_heatmap(all_preds: dict, n_users: int):
    if not MATCHES.empty and n_users > 0:
        coverage = {}
        for uid_preds in all_preds.values():
            for mid in uid_preds:
                coverage[mid] = coverage.get(mid, 0) + 1
        rows = []
        for row in MATCHES.itertuples(index=False):
            cnt = coverage.get(row.match_id, 0)
            rows.append({
                "ID":      row.match_id,
                "Partido": f"{row.home} vs {row.away}",
                "Etapa":   stage_label_from_bucket(str(row.group)),
                "Grupo/Ronda": bucket_label(row),
                "Pronósticos": cnt,
                "Cobertura %": round((cnt / n_users) * 100),
            })
        df_cov = pd.DataFrame(rows).sort_values("Cobertura %")
        st.dataframe(
            df_cov,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Cobertura %": st.column_config.ProgressColumn(
                    "Cobertura %", min_value=0, max_value=100, format="%d%%"
                ),
                "Pronósticos": st.column_config.NumberColumn(width="small"),
                "Etapa":       st.column_config.TextColumn(width="medium"),
                "Grupo/Ronda": st.column_config.TextColumn(width="medium"),
                "ID":          st.column_config.TextColumn(width="small"),
            },
        )
        sin_pron = sum(1 for r in rows if r["Pronósticos"] == 0)
        if sin_pron:
            st.warning(f"⚠️ {sin_pron} partidos sin ningún pronóstico registrado.")

# ──────────────────────────────────────────────────────────────
# AUTENTICACIÓN
# ──────────────────────────────────────────────────────────────
def register_user(username: str, pw: str) -> tuple[bool, str]:
    username = normalize_username(username)
    if not username or not pw:
        return False, "Completa ambos campos."
    if not USERNAME_RE.fullmatch(username):
        return False, "3–40 caracteres: letras, números, punto, guion o espacio."
    if len(pw) < 8:
        return False, "Contraseña mínimo 8 caracteres."
    if STORE.get_user(username):
        return False, "Ese nombre de usuario ya existe."
    STORE.create_user(username, make_password_hash(pw))
    STORE.append_audit(username, "user_registered", {"username": user_key(username)})
    invalidate_cache()
    return True, "Cuenta creada. Ahora inicia sesión."

def login_user(username: str, pw: str) -> tuple[bool, str]:
    username = normalize_username(username)
    record   = STORE.get_user(username)
    if not record or not verify_password(pw, record.get("password_hash", "")):
        return False, "Credenciales incorrectas."
    if not record["password_hash"].startswith("pbkdf2_sha256$"):
        STORE.update_user_hash(username, make_password_hash(pw))
    st.session_state.logged_in    = True
    st.session_state.current_user = record["username"]
    return True, "Sesión iniciada."

# ──────────────────────────────────────────────────────────────
# SESSION STATE
# ──────────────────────────────────────────────────────────────
for _k, _d in {"logged_in": False, "current_user": "", "is_admin": False}.items():
    st.session_state.setdefault(_k, _d)

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-banner">
  <div class="hero-kicker">
    <span class="hero-pill">⚽ Mundial FIFA 2026</span>
    <span class="hero-pill">🏛️ Posgrado IMP</span>
    <span class="hero-pill">🎯 Quinela institucional</span>
  </div>
  <h1 class="hero-title">Quinela Mundial 2026</h1>
  <p class="hero-subtitle">Pronostica fase de grupos y eliminatorias hasta la final.</p>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────
USERS, ALL_PREDS, RESULTS, LOCKS, ALL_SPECIAL_PREDS, SPECIAL_RESULTS = get_live_data()
STANDINGS = build_standings(USERS, ALL_PREDS, RESULTS)

with st.sidebar:
    st.markdown("### 🔑 Acceso")

    if not st.session_state.logged_in:
        tab_login, tab_reg = st.tabs(["Entrar", "Registrarse"])

        with tab_login:
            u_in = st.text_input("Usuario", key="login_u")
            p_in = st.text_input("Contraseña", type="password", key="login_p")
            if st.button("Iniciar sesión", use_container_width=True, key="login_button"):
                ok, msg = login_user(u_in, p_in)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

        with tab_reg:
            if not ENABLE_REGISTRATION:
                st.info("Registro cerrado. Solicita acceso al administrador.")
            else:
                u_r = st.text_input("Nombre de usuario", placeholder="Nombre Apellido", key="reg_u")
                p_r = st.text_input("Contraseña (mín. 8)", type="password", key="reg_p")
                if st.button("Crear cuenta", use_container_width=True, key="register_button"):
                    ok, msg = register_user(u_r, p_r)
                    (st.success if ok else st.error)(msg)
    else:
        current_user = st.session_state.current_user

        # Métricas personales — busca por _ukey para evitar bug con acentos
        my_ukey   = user_key(current_user)
        my_preds  = STORE.get_predictions(current_user)
        my_row_df = (
            STANDINGS[STANDINGS["_ukey"] == my_ukey]
            if not STANDINGS.empty and "_ukey" in STANDINGS.columns
            else pd.DataFrame()
        )
        my_pts  = int(my_row_df.iloc[0]["Puntos"])    if not my_row_df.empty else 0
        my_eval = int(my_row_df.iloc[0]["Evaluados"]) if not my_row_df.empty else 0
        my_pos  = int(my_row_df.index[0]) + 1         if not my_row_df.empty else "-"

        # Avatar con inicial + posición + puntos
        render_user_avatar(current_user, my_pts, my_pos)

        # Métrica compacta restante
        st.markdown(f"""
        <div class="metric-card">
          <div class="label">Pronosticados / Evaluados</div>
          <div class="value">{len(my_preds)} / {my_eval}</div>
        </div>
        """, unsafe_allow_html=True)

        # Barra de progreso
        if TOTAL_MATCHES > 0:
            pct = len(my_preds) / TOTAL_MATCHES
            st.progress(pct, text=f"{len(my_preds)} de {TOTAL_MATCHES} partidos pronosticados")

        if st.button("Cerrar sesión", use_container_width=True, key="logout_button"):
            st.session_state.logged_in    = False
            st.session_state.current_user = ""
            st.session_state.is_admin     = False
            st.rerun()

    st.divider()
    st.caption(
        f"🎯 Marcador exacto = **{POINTS_EXACT} pts**\n\n"
        f"✅ Resultado correcto = **{POINTS_RESULT} pt(s)**\n\n"
        "❌ Fallo = **0 pts**\n\n"
        "🔒 Los pronósticos se bloquean al inicio de cada partido o manualmente en eliminatorias."
    )
    sb_icon = "☁️" if isinstance(STORE, SupabaseStore) else "💾"
    st.caption(f"{sb_icon} Base de datos: **{STORE.name}** · 🕐 Zona: **{APP_TZ_NAME}**")
    if isinstance(STORE, LocalStore):
        st.info("Modo local activo. Configura Supabase en Secrets para producción.", icon="ℹ️")

# ──────────────────────────────────────────────────────────────
# PESTAÑAS
# ──────────────────────────────────────────────────────────────
tab_table, tab_preds, tab_results_tab, tab_bracket_tab, tab_rules_tab, tab_admin_tab = st.tabs([
    "🏆 Tablas y Premios", "📝 Mis Pronósticos", "📊 Resultados", "🧬 Eliminatorias", "📘 Reglamento", "⚙️ Administración"
])

# ════════════════════════════════════════
# 1 · TABLAS Y PREMIOS POR ETAPA
# ════════════════════════════════════════
with tab_table:
    render_section_title(
        "Tablas por etapa",
        "Ranking independiente para fase de grupos y eliminatorias, más distinciones automáticas y tabla global de referencia."
    )

    render_countdown()

    GROUP_STANDINGS = build_stage_standings(USERS, ALL_PREDS, RESULTS, "grupos")
    KO_STANDINGS = build_stage_standings(
        USERS, ALL_PREDS, RESULTS, "eliminatorias",
        include_specials=True,
        all_special_preds=ALL_SPECIAL_PREDS,
        special_results=SPECIAL_RESULTS,
    )
    GLOBAL_STANDINGS = build_global_standings_with_specials(
        USERS, ALL_PREDS, RESULTS, ALL_SPECIAL_PREDS, SPECIAL_RESULTS
    )

    n_bloqueados = (
        sum(1 for r in MATCHES.itertuples(index=False) if is_locked(r, LOCKS, RESULTS))
        if not MATCHES.empty else 0
    )
    k1, k2, k3, k4, k5 = st.columns(5)
    render_kpi(k1, "Resultados", f"{len(RESULTS)} / {TOTAL_MATCHES}", "Marcadores oficiales cargados", "📊")
    render_kpi(k2, "Participantes", len(USERS), "Usuarios registrados", "👥")
    render_kpi(k3, "Pronósticos", sum(len(v) for v in ALL_PREDS.values()), "Marcadores guardados", "📝")
    render_kpi(k4, "Bloqueados", n_bloqueados, "Partidos cerrados a edición", "🔒")
    render_kpi(k5, "Premios especiales", len(SPECIAL_RESULTS), f"Acierto vale {POINTS_SPECIAL} pts por defecto", "🏅")

    st.write("")
    t_groups, t_ko, t_global, t_stats = st.tabs([
        "🌎 Fase de grupos", "🏆 Eliminatorias", "📌 Global", "📈 Estadísticas"
    ])

    with t_groups:
        render_stage_table(
            "Tabla · Fase de grupos",
            "Solo considera los partidos M001–M072. Ideal para premiar al mejor desempeño de la primera etapa.",
            GROUP_STANDINGS,
            "tabla_fase_grupos.csv",
        )
        st.markdown("#### Distinciones de la primera etapa")
        awards = group_award_rows(GROUP_STANDINGS)
        if not awards:
            render_empty_state("🎖️", "Aún no hay distinciones", "Carga resultados de fase de grupos para activar las menciones automáticas.")
        else:
            for i in range(0, len(awards), 3):
                cols = st.columns(3)
                for j, col in enumerate(cols):
                    if i + j < len(awards):
                        a = awards[i + j]
                        render_award_card(col, a["icon"], a["label"], a["winner"], a["meta"])

    with t_ko:
        render_stage_table(
            "Tabla · Eliminatorias",
            "Suma los partidos M073–M104 y los puntos de premios especiales cuando el administrador cargue los ganadores oficiales.",
            KO_STANDINGS,
            "tabla_eliminatorias.csv",
        )
        st.markdown("#### Premios especiales de eliminatorias / torneo")
        if not SPECIAL_RESULTS:
            st.info("Aún no hay premios oficiales cargados. Los usuarios pueden registrar sus pronósticos en la pestaña Mis Pronósticos.")
        special_rows = []
        for c in SPECIAL_CATEGORIES:
            official = SPECIAL_RESULTS.get(c["key"], {})
            total_preds = sum(1 for preds in ALL_SPECIAL_PREDS.values() if preds.get(c["key"], {}).get("value"))
            hits = 0
            if official.get("value"):
                for preds in ALL_SPECIAL_PREDS.values():
                    pred = preds.get(c["key"], {})
                    if pred.get("value") and _norm_answer(pred.get("value")) == _norm_answer(official.get("value")):
                        hits += 1
            special_rows.append({
                "Premio": f"{c['icon']} {c['label']}",
                "Oficial": official.get("value", "—"),
                "Puntos": int(official.get("points", POINTS_SPECIAL)) if official else POINTS_SPECIAL,
                "Pronósticos": total_preds,
                "Aciertos": hits if official.get("value") else "—",
            })
        st.dataframe(pd.DataFrame(special_rows), use_container_width=True, hide_index=True)

    with t_global:
        render_stage_table(
            "Tabla global de referencia",
            "Suma fase de grupos, eliminatorias y bonus de premios especiales. La premiación puede usar tablas separadas por etapa.",
            GLOBAL_STANDINGS,
            "tabla_global_quinela.csv",
        )
        if not GLOBAL_STANDINGS.empty and len(RESULTS) > 0:
            st.markdown("#### Top 10 global")
            render_top10_chart(GLOBAL_STANDINGS)

    with t_stats:
        render_section_title("Estadísticas generales", "Lectura rápida del avance y desempeño de la quinela.")
        if GROUP_STANDINGS.empty and KO_STANDINGS.empty:
            render_empty_state("📈", "Sin estadísticas todavía", "Cuando haya pronósticos y resultados, aquí aparecerán los líderes por rubro.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### Fase de grupos")
                stats_cols = st.columns(2)
                if not GROUP_STANDINGS.empty:
                    top_exact = GROUP_STANDINGS.sort_values(["Exactos 🎯", "Puntos"], ascending=False).iloc[0]
                    top_avg = GROUP_STANDINGS[GROUP_STANDINGS["Evaluados"] > 0].sort_values(["Promedio", "Puntos"], ascending=False)
                    render_award_card(stats_cols[0], "🎯", "Líder en exactos", str(top_exact["Usuario"]), f"{int(top_exact['Exactos 🎯'])} marcadores exactos")
                    if not top_avg.empty:
                        r = top_avg.iloc[0]
                        render_award_card(stats_cols[1], "📈", "Mejor promedio", str(r["Usuario"]), f"{float(r['Promedio']):.2f} pts/partido")
            with c2:
                st.markdown("##### Eliminatorias")
                stats_cols = st.columns(2)
                if not KO_STANDINGS.empty:
                    top_ko = KO_STANDINGS.iloc[0]
                    top_bonus = KO_STANDINGS.sort_values(["Bonus premios", "Puntos"], ascending=False).iloc[0]
                    render_award_card(stats_cols[0], "🏆", "Líder eliminatorias", str(top_ko["Usuario"]), f"{int(top_ko['Puntos'])} pts")
                    render_award_card(stats_cols[1], "🏅", "Más bonus de premios", str(top_bonus["Usuario"]), f"{int(top_bonus['Bonus premios'])} pts bonus")

# ════════════════════════════════════════
# 2 · MIS PRONÓSTICOS
# ════════════════════════════════════════
with tab_preds:
    render_section_title(
        "Mis pronósticos",
        "Completa tus marcadores antes de que cada partido se bloquee."
    )

    if not st.session_state.logged_in:
        st.warning("⚠️ Inicia sesión para registrar o modificar tus pronósticos.")
    elif MATCHES.empty:
        st.error("No se cargó el calendario de partidos.")
    else:
        current_user = st.session_state.current_user
        my_preds     = STORE.get_predictions(current_user)
        pending_count = max(0, TOTAL_MATCHES - len(my_preds))
        st.markdown(f"""
        <div class="quick-card">
          <strong>Tu avance:</strong> {len(my_preds)} de {TOTAL_MATCHES} partidos pronosticados ·
          <strong>{pending_count}</strong> pendientes. Usa los filtros para moverte entre grupos y eliminatorias.
        </div>
        """, unsafe_allow_html=True)

        stage_df = stage_progress_df(my_preds)
        st.markdown("#### Avance por etapa")
        st.dataframe(
            stage_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Avance": st.column_config.ProgressColumn("Avance", min_value=0, max_value=100, format="%d%%"),
                "Etapa": st.column_config.TextColumn(width="medium"),
            },
        )

        with st.expander("🏅 Pronósticos especiales de eliminatorias / torneo", expanded=True):
            st.caption(
                "Estos pronósticos funcionan como bonus de segunda etapa. Se evalúan cuando el administrador carga el ganador oficial de cada premio. "
                "Una vez cargado el resultado oficial de un premio, ese pronóstico queda cerrado."
            )
            my_specials = STORE.get_special_predictions(current_user)
            team_opts = _team_options()

            for i in range(0, len(SPECIAL_CATEGORIES), 3):
                cols = st.columns(3)
                for j, col in enumerate(cols):
                    if i + j >= len(SPECIAL_CATEGORIES):
                        continue
                    cat = SPECIAL_CATEGORIES[i + j]
                    key = cat["key"]
                    official = SPECIAL_RESULTS.get(key, {})
                    existing = my_specials.get(key, {}).get("value", "")
                    locked_special = bool(official.get("value"))
                    with col:
                        st.markdown(f"""
                        <div class="special-card">
                          <div class="special-label">{cat['icon']} {cat['label']}</div>
                          <div class="special-help">{cat['help']}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        if locked_special:
                            st.success(f"Oficial: {official.get('value')} · {int(official.get('points', POINTS_SPECIAL))} pts")
                            if existing:
                                ok = _norm_answer(existing) == _norm_answer(official.get("value"))
                                st.info(f"Tu pronóstico: **{existing}** · {'✅ acierto' if ok else '❌ no acertó'}")
                            else:
                                st.caption("Sin pronóstico registrado antes del cierre.")
                            continue

                        with st.form(key=f"sp_{key}"):
                            if cat["kind"] == "team" and team_opts:
                                options = [""] + team_opts + ["Otro / escribir manualmente"]
                                default_idx = options.index(existing) if existing in options else 0
                                sel = st.selectbox(cat["label"], options, index=default_idx, key=f"sp_sel_{key}")
                                manual = ""
                                if sel == "Otro / escribir manualmente" or (existing and existing not in options):
                                    manual = st.text_input("Escribir opción", value=existing if existing not in team_opts else "", key=f"sp_txt_{key}")
                                value = manual.strip() if manual.strip() else sel.strip()
                            else:
                                value = st.text_input(cat["label"], value=existing, placeholder="Nombre del jugador / selección", key=f"sp_txt_{key}")
                            if st.form_submit_button("Guardar", use_container_width=True):
                                if not value.strip():
                                    st.warning("Escribe o selecciona un pronóstico.")
                                else:
                                    STORE.upsert_special_prediction(current_user, key, value)
                                    STORE.append_audit(current_user, "special_prediction_saved", {"category": key})
                                    invalidate_cache()
                                    st.success("Pronóstico especial guardado ✓")
                                    st.rerun()

        with st.expander("📈 Ver avance detallado por grupo", expanded=False):
            gp = group_progress_df(my_preds)
            st.dataframe(
                gp,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Avance": st.column_config.ProgressColumn("Avance", min_value=0, max_value=100, format="%d%%"),
                    "Grupo": st.column_config.TextColumn(width="small"),
                },
            )

        fc1, fc2, fc3, fc4 = st.columns([1.15, 1.35, 2, 1.5])
        stage_filter = fc1.selectbox("Etapa", ["Todas", "Grupos", "Eliminatorias"], key="f_stage")
        g_filter = fc2.selectbox("Grupo/Ronda", ["Todos"] + BUCKETS, key="f_group", format_func=bucket_format)
        t_filter = fc3.text_input("Buscar equipo", placeholder="México, Brasil, Ganador M073…", key="f_text")
        s_filter = fc4.selectbox(
            "Estado", ["Todos", "Abiertos", "Bloqueados", "Con resultado"], key="f_status"
        )

        def match_visible(row):
            locked     = is_locked(row, LOCKS, RESULTS)
            has_result = row.match_id in RESULTS
            if stage_filter == "Grupos" and not is_group_stage(row):
                return False
            if stage_filter == "Eliminatorias" and not is_knockout_stage(row):
                return False
            if g_filter != "Todos" and row.group != g_filter:
                return False
            if t_filter and t_filter.casefold() not in f"{row.home} {row.away} {row.match_id}".casefold():
                return False
            if s_filter == "Abiertos"      and locked:         return False
            if s_filter == "Bloqueados"    and not locked:     return False
            if s_filter == "Con resultado" and not has_result: return False
            return True

        filtered = [r for r in MATCHES.itertuples(index=False) if match_visible(r)]

        if not filtered:
            render_empty_state("🔎", "Sin coincidencias", "Ajusta el grupo, el estado o la búsqueda de equipo para encontrar partidos.")
        else:
            by_date: dict[str, list] = {}
            for row in filtered:
                by_date.setdefault(row.match_date, []).append(row)

            for date_str, matches_day in sorted(by_date.items()):
                abiertos = sum(1 for r in matches_day if not is_locked(r, LOCKS, RESULTS))
                ya_pron  = sum(1 for r in matches_day if r.match_id in my_preds)
                label    = f"📅 {date_str}  ·  {len(matches_day)} partidos"
                if abiertos:
                    label += f"  ·  🟢 {abiertos} abiertos"
                label += f"  ·  📝 {ya_pron} pronosticados"

                with st.expander(label, expanded=(abiertos > 0)):
                    for start in range(0, len(matches_day), 2):
                        cols = st.columns(2)
                        for offset, col in enumerate(cols):
                            if start + offset >= len(matches_day):
                                continue
                            row    = matches_day[start + offset]
                            pred   = my_preds.get(row.match_id)
                            result = RESULTS.get(row.match_id)
                            locked = is_locked(row, LOCKS, RESULTS)

                            with col:
                                with st.container(border=True):
                                    # Usa el componente centralizado (elimina duplicación)
                                    render_match_card_header(row, LOCKS, RESULTS)

                                    if result:
                                        st.markdown(
                                            f'''<div class="score-line official">
                                                <div class="score-title">Resultado oficial</div>
                                                <div class="score-value">{result['home_goals']} – {result['away_goals']}</div>
                                            </div>''',
                                            unsafe_allow_html=True,
                                        )
                                    if pred:
                                        line = f"{pred['home_goals']} – {pred['away_goals']}"
                                        extra = ""
                                        if result:
                                            pts = calc_pts(
                                                int(pred["home_goals"]), int(pred["away_goals"]),
                                                int(result["home_goals"]), int(result["away_goals"]),
                                            )
                                            extra = f" · {pts_label(pts)}"
                                        st.markdown(
                                            f'''<div class="score-line">
                                                <div class="score-title">Tu pronóstico</div>
                                                <div class="score-value">{line}{extra}</div>
                                            </div>''',
                                            unsafe_allow_html=True,
                                        )

                                    if locked:
                                        if not pred:
                                            st.caption("Sin pronóstico registrado antes del bloqueo.")
                                        continue

                                    with st.form(key=f"pf_{row.match_id}"):
                                        a, b = st.columns(2)
                                        dh = int(pred["home_goals"]) if pred else 0
                                        da = int(pred["away_goals"]) if pred else 0
                                        gh = a.number_input(
                                            row.home[:14],
                                            min_value=0,
                                            max_value=30,
                                            value=dh,
                                            key=f"pred_home_{row.match_id}",
                                        )
                                        ga = b.number_input(
                                            row.away[:14],
                                            min_value=0,
                                            max_value=30,
                                            value=da,
                                            key=f"pred_away_{row.match_id}",
                                        )
                                        if st.form_submit_button("💾 Guardar", use_container_width=True):
                                            # Revalidar bloqueo al momento del submit
                                            if is_locked(row, STORE.list_locks(), STORE.list_results()):
                                                st.error("El partido se bloqueó al enviar. No se guardó.")
                                            else:
                                                STORE.upsert_prediction(current_user, row.match_id, int(gh), int(ga))
                                                invalidate_cache()
                                                st.success("Pronóstico guardado ✓")
                                                st.rerun()

# ════════════════════════════════════════
# 3 · RESULTADOS  (FIX: muestra todos los partidos, con y sin resultado)
# ════════════════════════════════════════
with tab_results_tab:
    render_section_title(
        "Resultados oficiales",
        "Consulta marcadores cargados, sedes y avance del calendario."
    )

    rr1, rr2, rr3, rr4 = st.columns(4)
    render_kpi(rr1, "Con resultado", f"{len(RESULTS)} / {TOTAL_MATCHES}", f"{pct_txt(len(RESULTS), TOTAL_MATCHES)} del calendario", "✅")
    render_kpi(rr2, "Pendientes", max(0, TOTAL_MATCHES - len(RESULTS)), "Partidos sin marcador oficial", "⏳")
    render_kpi(rr3, "Grupos", GROUP_MATCHES, "Primera etapa", "🌎")
    render_kpi(rr4, "Eliminatorias", KNOCKOUT_MATCHES, "Segunda etapa", "🏆")

    rc1, rc2, rc3 = st.columns([1.1, 1.4, 2.5])
    res_stage = rc1.selectbox("Etapa", ["Todas", "Grupos", "Eliminatorias"], key="res_stage")
    rg        = rc2.selectbox("Grupo/Ronda", ["Todos"] + BUCKETS, key="res_group", format_func=bucket_format)
    show_all  = rc3.checkbox("Mostrar también partidos sin resultado", value=False, key="res_show_all")

    rows_res = []
    for row in MATCHES.itertuples(index=False):
        if res_stage == "Grupos" and not is_group_stage(row):
            continue
        if res_stage == "Eliminatorias" and not is_knockout_stage(row):
            continue
        if rg != "Todos" and row.group != rg:
            continue
        res = RESULTS.get(row.match_id)
        if not res and not show_all:
            continue
        rows_res.append({
            "Etapa":      stage_label_from_bucket(str(row.group)),
            "Grupo/Ronda": bucket_label(row),
            "ID":         row.match_id,
            "Local":      row.home,
            "Resultado":  f"{res['home_goals']} – {res['away_goals']}" if res else "—",
            "Visitante":  row.away,
            "Sede":       row.venue,
            "Fecha":      row.match_date,
        })
    if rows_res:
        st.dataframe(
            pd.DataFrame(rows_res),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Resultado": st.column_config.TextColumn(width="small"),
                "ID":        st.column_config.TextColumn(width="small"),
                "Etapa":     st.column_config.TextColumn(width="medium"),
                "Grupo/Ronda": st.column_config.TextColumn(width="medium"),
            },
        )
        st.caption(f"Mostrando {len(rows_res)} partidos · {len(RESULTS)} con resultado cargado.")
    else:
        render_empty_state("📊", "Sin resultados para este filtro", "Activa la casilla para ver partidos sin resultado o selecciona otro grupo.")

# ════════════════════════════════════════
# 4 · ELIMINATORIAS / BRACKET
# ════════════════════════════════════════
with tab_bracket_tab:
    render_section_title(
        "Etapa de eliminatorias",
        "Visualiza 16avos, octavos, cuartos, semifinales, tercer lugar y final. Los placeholders se actualizan en matches_2026.csv cuando se definan los clasificados."
    )

    b1, b2, b3, b4 = st.columns(4)
    ko_results = sum(1 for r in MATCHES.itertuples(index=False) if is_knockout_stage(r) and r.match_id in RESULTS)
    ko_locked  = sum(1 for r in MATCHES.itertuples(index=False) if is_knockout_stage(r) and is_locked(r, LOCKS, RESULTS))
    render_kpi(b1, "Partidos", KNOCKOUT_MATCHES, "De M073 a M104", "🏆")
    render_kpi(b2, "Rondas", len(KNOCKOUT_ROUNDS), "16avos a final", "🧬")
    render_kpi(b3, "Con resultado", f"{ko_results} / {KNOCKOUT_MATCHES}", "Marcadores cargados", "✅")
    render_kpi(b4, "Bloqueados", ko_locked, "Cerrados a edición", "🔒")

    if KNOCKOUT_MATCHES == 0:
        render_empty_state("🧬", "Sin eliminatorias cargadas", "Agrega los partidos M073–M104 en matches_2026.csv.")
    else:
        for rnd in KNOCKOUT_ROUNDS:
            rnd_matches = [r for r in MATCHES.itertuples(index=False) if r.group == rnd]
            with st.expander(f"{rnd} · {len(rnd_matches)} partidos", expanded=(rnd in ["16avos", "Octavos"])):
                for start in range(0, len(rnd_matches), 2):
                    cols = st.columns(2)
                    for offset, col in enumerate(cols):
                        if start + offset >= len(rnd_matches):
                            continue
                        row = rnd_matches[start + offset]
                        res = RESULTS.get(row.match_id)
                        with col:
                            result_txt = f" · Resultado: {res['home_goals']}–{res['away_goals']}" if res else ""
                            st.markdown(f"""
                            <div class="bracket-card">
                              <div class="round">{row.match_id} · {rnd}</div>
                              <div class="teams">{row.home} <span style="color:var(--gris)">vs</span> {row.away}</div>
                              <div class="meta">📅 {fmt_kickoff(row)} · 📍 {row.venue}{result_txt}</div>
                            </div>
                            """, unsafe_allow_html=True)

# ════════════════════════════════════════
# 5 · REGLAMENTO  (generado dinámicamente)
# ════════════════════════════════════════
with tab_rules_tab:
    render_section_title(
        "Reglamento de la quinela",
        "Reglas oficiales, sistema de puntos y criterios de desempate."
    )

    # Tarjetas de puntos con diseño del sistema
    r1, r2, r3, r4 = st.columns(4)
    render_kpi(r1, "Marcador exacto",    POINTS_EXACT,  "Adivinaste el resultado y el marcador", "🎯")
    render_kpi(r2, "Resultado correcto", POINTS_RESULT, "Adivinaste quién ganó (o empate)", "✅")
    render_kpi(r3, "Premio especial",    POINTS_SPECIAL, "Valor por defecto configurable", "🏅")
    render_kpi(r4, "Puntos máximos",     TOTAL_MATCHES * POINTS_EXACT + len(SPECIAL_CATEGORIES) * POINTS_SPECIAL, f"{GROUP_MATCHES} grupos + {KNOCKOUT_MATCHES} eliminatorias + premios", "🏆")

    st.markdown(f"""
---
#### Desempates *(en orden de prioridad)*

| Prioridad | Criterio |
|---:|---|
| 1 | Mayor número de **puntos totales** |
| 2 | Mayor número de marcadores **exactos** (+{POINTS_EXACT} pts) |
| 3 | Mayor número de **resultados acertados** (+{POINTS_RESULT} pt) |
| 4 | Menor suma de diferencias absolutas de goles |
| 5 | Mayor cantidad de partidos pronosticados |

---
#### Dos etapas de competencia

La quinela considera **fase de grupos** y **eliminatorias**: 16avos, octavos, cuartos, semifinales, partido por tercer lugar y final.

- **Tabla de fase de grupos:** solo suma M001–M072. Incluye menciones automáticas como más marcadores exactos, más aciertos, mejor efectividad y mejor diferencia acumulada.
- **Tabla de eliminatorias:** suma M073–M104 y los **premios especiales** cuando el administrador capture los ganadores oficiales.
- **Tabla global:** es una referencia acumulada de ambas etapas y los bonus especiales.

#### Bloqueo de pronósticos

Cada partido se bloquea **automáticamente** al llegar su hora de inicio si `kickoff_at` está definido.
Si la hora no está definida —especialmente en eliminatorias— el administrador puede bloquear manualmente desde el panel.
Una vez bloqueado, el pronóstico **ya no puede modificarse**.

#### Edición libre hasta el cierre

Puedes cambiar tu pronóstico **cuantas veces quieras** mientras el partido esté abierto.
Siempre se guarda el último valor confirmado.

#### Premios especiales de segunda etapa

Incluyen campeón, subcampeón, tercer lugar, Balón de Oro, Bota de Oro, Guante de Oro, mejor joven, Fair Play y caballo negro. Cada categoría se bloquea cuando el administrador publica el ganador oficial de esa categoría. El puntaje puede ajustarse desde administración; por defecto vale **{POINTS_SPECIAL} pts**.

---
*{TOTAL_MATCHES} partidos · 2 etapas · {GROUP_MATCHES} de grupos + {KNOCKOUT_MATCHES} de eliminatorias*
    """)

    if CALENDAR_WARNINGS:
        st.warning("⚠️ Revisión de calendario: " + " | ".join(CALENDAR_WARNINGS))

# ════════════════════════════════════════
# 6 · ADMINISTRACIÓN
# ════════════════════════════════════════
with tab_admin_tab:
    st.subheader("Panel de administración")

    if not ADMIN_PASSWORD and not ADMIN_PASSWORD_HASH:
        st.warning(
            "⚠️ No hay contraseña de admin configurada. "
            "Agrega `ADMIN_PASSWORD` (o `ADMIN_PASSWORD_HASH`) en los Secrets de Streamlit."
        )

    if not st.session_state.is_admin:
        ap = st.text_input("Contraseña de administrador", type="password", key="adm_pw")
        if st.button("Entrar como admin", use_container_width=True, key="admin_login_button"):
            if verify_admin(ap):
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")

    if st.session_state.is_admin:
        st.success("✅ Modo administrador activo")

        adm_res_tab, adm_lock_tab, adm_special_tab, adm_users_tab, adm_coverage_tab, adm_audit_tab, adm_export_tab = st.tabs([
            "Resultados", "Bloqueos manuales", "Premios especiales", "Participantes", "Cobertura", "Auditoría", "Respaldo"
        ])

        # ── Resultados ────────────────────────────────────────
        with adm_res_tab:
            st.markdown("#### Publicar o corregir resultado oficial")
            st.caption("Publicar activa el bloqueo automáticamente en una sola operación.")

            if not MATCHES.empty:
                adm_g         = st.selectbox("Grupo/Ronda", BUCKETS, key="adm_group", format_func=bucket_format)
                group_matches = [r for r in MATCHES.itertuples(index=False) if r.group == adm_g]
                pendientes    = sum(1 for r in group_matches if r.match_id not in RESULTS)
                st.info(f"Partidos sin resultado en {bucket_label_from_value(adm_g)}: **{pendientes}**")

                adm_idx = st.selectbox(
                    "Partido",
                    range(len(group_matches)),
                    format_func=lambda i: (
                        f"{group_matches[i].match_id} · "
                        f"{group_matches[i].home} vs {group_matches[i].away}"
                        + (" ✅" if group_matches[i].match_id in RESULTS else "")
                    ),
                    key="adm_match",
                )
                sel      = group_matches[adm_idx]
                existing = RESULTS.get(sel.match_id, {})
                if existing:
                    st.warning(
                        f"Resultado actual: **{existing['home_goals']} – {existing['away_goals']}**. "
                        "Se sobreescribirá."
                    )

                ca, cb = st.columns(2)
                rh = ca.number_input(f"Goles {sel.home}", min_value=0, max_value=30,
                                     value=int(existing.get("home_goals", 0)), key="adm_rh")
                ra = cb.number_input(f"Goles {sel.away}", min_value=0, max_value=30,
                                     value=int(existing.get("away_goals", 0)), key="adm_ra")

                if st.button("📥 Publicar resultado", use_container_width=True, type="primary", key=f"adm_publish_result_{sel.match_id}"):
                    ok, msg = STORE.publish_result(sel.match_id, int(rh), int(ra))
                    if ok:
                        STORE.append_audit(
                            st.session_state.current_user or "admin", "result_published",
                            {"match_id": sel.match_id, "home": int(rh), "away": int(ra)},
                        )
                        invalidate_cache()
                        st.success(f"✅ {sel.home} **{rh}** – **{ra}** {sel.away}")
                        st.rerun()
                    else:
                        st.error(f"Error: {msg}")

                st.divider()
                st.markdown("#### Eliminar resultado")
                if RESULTS:
                    del_id = st.selectbox(
                        "Resultado a eliminar", list(RESULTS.keys()),
                        format_func=lambda mid: (
                            f"{mid} · {MATCH_IDX[mid].home} vs {MATCH_IDX[mid].away}"
                            if mid in MATCH_IDX else mid
                        ),
                        key="del_id",
                    )
                    if st.button("🗑️ Eliminar resultado", type="secondary", key=f"adm_delete_result_{del_id}"):
                        STORE.delete_result(del_id)
                        STORE.append_audit(
                            st.session_state.current_user or "admin", "result_deleted",
                            {"match_id": del_id},
                        )
                        invalidate_cache()
                        st.success("Resultado eliminado. El bloqueo manual se conserva.")
                        st.rerun()
                else:
                    st.caption("Sin resultados cargados.")

        # ── Bloqueos manuales ─────────────────────────────────
        with adm_lock_tab:
            st.markdown("#### Bloqueo manual de pronósticos")
            st.caption(
                "Úsalo cuando el partido inicia pero aún no tienes el resultado, "
                "o cuando `kickoff_at` no está definido en el CSV."
            )
            blk_g       = st.selectbox("Grupo/Ronda", BUCKETS, key="blk_group", format_func=bucket_format)
            blk_matches = [r for r in MATCHES.itertuples(index=False) if r.group == blk_g]

            blk_rows = []
            for r in blk_matches:
                auto     = parse_kickoff(getattr(r, "kickoff_at", ""))
                auto_blk = bool(auto and datetime.now(APP_TZ) >= auto)
                blk_rows.append({
                    "ID":            r.match_id,
                    "Partido":       f"{r.home} vs {r.away}",
                    "Auto (kickoff)": "🔒" if auto_blk else ("⏳" if auto else "—"),
                    "Manual":        "🔒" if LOCKS.get(r.match_id) else "🔓",
                    "Resultado":     "✅" if r.match_id in RESULTS else "—",
                })
            st.dataframe(pd.DataFrame(blk_rows), hide_index=True, use_container_width=True)

            blk_idx = st.selectbox(
                "Partido a bloquear/desbloquear",
                range(len(blk_matches)),
                format_func=lambda i: (
                    f"{blk_matches[i].match_id} · "
                    f"{blk_matches[i].home} vs {blk_matches[i].away}"
                ),
                key="blk_idx",
            )
            blk_row  = blk_matches[blk_idx]
            cur_lock = bool(LOCKS.get(blk_row.match_id, False))
            new_lock = st.toggle("Bloqueo manual activado", value=cur_lock, key="blk_toggle")
            if st.button("Guardar bloqueo", use_container_width=True, key=f"adm_save_lock_{blk_row.match_id}"):
                STORE.set_lock(blk_row.match_id, new_lock)
                STORE.append_audit(
                    st.session_state.current_user or "admin", "manual_lock_updated",
                    {"match_id": blk_row.match_id, "locked": bool(new_lock)},
                )
                invalidate_cache()
                st.success("Bloqueo actualizado.")
                st.rerun()

        # ── Premios especiales ─────────────────────────────────
        with adm_special_tab:
            st.markdown("#### Cargar ganadores oficiales de premios especiales")
            st.caption(
                "Estos premios suman puntos bonus a la tabla de eliminatorias. "
                "Al cargar un ganador oficial, el pronóstico queda cerrado para esa categoría."
            )
            cat_map = {c["key"]: c for c in SPECIAL_CATEGORIES}
            cat_key = st.selectbox(
                "Premio / pronóstico especial",
                [c["key"] for c in SPECIAL_CATEGORIES],
                format_func=lambda k: f"{cat_map[k]['icon']} {cat_map[k]['label']}",
                key="adm_special_cat",
            )
            cat = cat_map[cat_key]
            existing = SPECIAL_RESULTS.get(cat_key, {})
            st.info(f"{cat['help']} · Puntaje por defecto: {POINTS_SPECIAL} pts")
            team_opts = _team_options()
            if cat["kind"] == "team" and team_opts:
                options = [""] + team_opts + ["Otro / escribir manualmente"]
                old = existing.get("value", "")
                idx = options.index(old) if old in options else 0
                selected = st.selectbox("Ganador oficial", options, index=idx, key="adm_special_sel")
                manual_val = ""
                if selected == "Otro / escribir manualmente" or (old and old not in options):
                    manual_val = st.text_input("Escribir ganador oficial", value=old if old not in team_opts else "", key="adm_special_manual")
                official_val = manual_val.strip() if manual_val.strip() else selected.strip()
            else:
                official_val = st.text_input("Ganador oficial", value=existing.get("value", ""), key="adm_special_value")
            pts_special = st.number_input(
                "Puntos por acertar", min_value=0, max_value=50,
                value=int(existing.get("points", POINTS_SPECIAL) if existing else POINTS_SPECIAL),
                key="adm_special_points",
            )
            csave, cdel = st.columns(2)
            if csave.button("🏅 Guardar ganador oficial", type="primary", use_container_width=True, key=f"adm_save_special_{cat_key}"):
                if not official_val.strip():
                    st.error("Indica el ganador oficial.")
                else:
                    STORE.upsert_special_result(cat_key, official_val, int(pts_special))
                    STORE.append_audit(
                        st.session_state.current_user or "admin", "special_result_published",
                        {"category": cat_key, "value": official_val, "points": int(pts_special)},
                    )
                    invalidate_cache()
                    st.success("Premio especial guardado.")
                    st.rerun()
            if cdel.button("🗑️ Eliminar ganador oficial", type="secondary", use_container_width=True, key=f"adm_delete_special_{cat_key}"):
                STORE.delete_special_result(cat_key)
                STORE.append_audit(
                    st.session_state.current_user or "admin", "special_result_deleted",
                    {"category": cat_key},
                )
                invalidate_cache()
                st.success("Ganador oficial eliminado. Los usuarios podrán editar de nuevo esa categoría.")
                st.rerun()

            st.divider()
            st.markdown("#### Estado de premios especiales")
            rows = []
            for c in SPECIAL_CATEGORIES:
                official = SPECIAL_RESULTS.get(c["key"], {})
                total_preds = sum(1 for preds in ALL_SPECIAL_PREDS.values() if preds.get(c["key"], {}).get("value"))
                hits = 0
                if official.get("value"):
                    for preds in ALL_SPECIAL_PREDS.values():
                        pred = preds.get(c["key"], {})
                        if pred.get("value") and _norm_answer(pred.get("value")) == _norm_answer(official.get("value")):
                            hits += 1
                rows.append({
                    "Premio": f"{c['icon']} {c['label']}",
                    "Oficial": official.get("value", "—"),
                    "Puntos": int(official.get("points", POINTS_SPECIAL)) if official else POINTS_SPECIAL,
                    "Pronósticos": total_preds,
                    "Aciertos": hits if official.get("value") else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            sp_export = special_predictions_export(USERS, ALL_SPECIAL_PREDS, SPECIAL_RESULTS)
            if not sp_export.empty:
                st.download_button(
                    "⬇️ Descargar pronósticos especiales CSV",
                    data=sp_export.to_csv(index=False).encode("utf-8-sig"),
                    file_name="quinela_pronosticos_especiales.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="dl_special_predictions_csv",
                )

        # ── Participantes + reset de contraseña ───────────────
        with adm_users_tab:
            st.markdown("#### Avance por participante")
            if not STANDINGS.empty:
                users_df = STANDINGS.drop(columns=["_ukey"], errors="ignore").copy()
                st.dataframe(users_df, use_container_width=True, hide_index=True)
                st.download_button(
                    "⬇️ Descargar tabla CSV",
                    data=users_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name="quinela_participantes.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="dl_participants_csv",
                )
            else:
                st.info("Aún no hay participantes.")

            pred_export = build_predictions_export(USERS, ALL_PREDS, RESULTS)
            if not pred_export.empty:
                st.download_button(
                    "⬇️ Descargar todos los pronósticos CSV",
                    data=pred_export.to_csv(index=False).encode("utf-8-sig"),
                    file_name="quinela_pronosticos_detalle.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="dl_all_predictions_csv",
                )

            st.divider()
            st.markdown("#### Resetear contraseña de un participante")
            st.caption(
                "Útil cuando un usuario olvidó su contraseña. "
                "El usuario deberá iniciar sesión con la contraseña temporal y puede cambiarla."
            )
            if USERS:
                user_names = sorted(u["username"] for u in USERS)
                reset_u    = st.selectbox("Usuario", user_names, key="reset_user")
                reset_pw   = st.text_input(
                    "Nueva contraseña temporal (mín. 8 caracteres)",
                    type="password", key="reset_pw"
                )
                if st.button("🔑 Aplicar nueva contraseña", use_container_width=True, key=f"reset_password_{reset_u}"):
                    if len(reset_pw) < 8:
                        st.error("La contraseña debe tener al menos 8 caracteres.")
                    else:
                        STORE.update_user_hash(reset_u, make_password_hash(reset_pw))
                        STORE.append_audit(
                            st.session_state.current_user or "admin", "password_reset",
                            {"target_user": user_key(reset_u)},
                        )
                        invalidate_cache()
                        st.success(f"Contraseña de **{reset_u}** actualizada.")
            else:
                st.caption("Sin participantes registrados.")

        # ── Cobertura (heat map) ──────────────────────────────
        with adm_coverage_tab:
            st.markdown("#### Cobertura de pronósticos por partido")
            st.caption(
                "Muestra cuántos participantes pronosticaron cada partido. "
                "Los partidos con cobertura baja pueden necesitar un recordatorio."
            )
            n_users = len(USERS)
            if n_users == 0:
                render_empty_state("📊", "Sin participantes aún", "Cuando haya usuarios registrados, aquí aparecerá la cobertura por partido.")
            else:
                render_coverage_heatmap(ALL_PREDS, n_users)

        # ── Auditoría ─────────────────────────────────────────
        with adm_audit_tab:
            st.markdown("#### Bitácora de cambios")
            audit_rows = STORE.list_audit(150)
            if audit_rows:
                audit_df = pd.DataFrame(audit_rows)
                if "detail" in audit_df.columns:
                    audit_df["detail"] = audit_df["detail"].apply(
                        lambda x: json.dumps(x, ensure_ascii=False)
                        if isinstance(x, (dict, list)) else str(x)
                    )
                st.dataframe(audit_df, use_container_width=True, hide_index=True)
            else:
                st.info("Sin eventos de auditoría registrados aún.")

        # ── Respaldo ─────────────────────────────────────────
        with adm_export_tab:
            st.markdown("#### Respaldo de datos")
            if CALENDAR_WARNINGS:
                st.warning("⚠️ Calendario: " + " | ".join(CALENDAR_WARNINGS))
            payload = json.dumps(
                STORE.export_all(), ensure_ascii=False, indent=2, default=str
            )
            st.download_button(
                "⬇️ Descargar respaldo JSON",
                data=payload,
                file_name=f"quinela_backup_{datetime.now(APP_TZ).strftime('%Y%m%d_%H%M')}.json",
                mime="application/json",
                use_container_width=True,
                key="dl_backup_json",
            )
            st.download_button(
                "⬇️ Descargar calendario CSV",
                data=MATCHES.to_csv(index=False).encode("utf-8"),
                file_name="matches_2026.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_calendar_csv",
            )

        if st.button("Salir de administración", type="secondary", key="adm_logout_button"):
            st.session_state.is_admin = False
            st.rerun()
