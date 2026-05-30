"""
Quinela Mundial 2026 · Posgrado IMP
=====================================
v5 — Correcciones sobre v4:
  - Cache de datos vivos con TTL corto (evita lecturas repetidas por recarga)
  - Bug fix: búsqueda de posición en sidebar usa user_key consistentemente
  - Tab Resultados muestra todos los partidos (con y sin resultado)
  - Barra de progreso de pronósticos por usuario
  - Admin: reset de contraseña de participantes
  - get_store() sin cache_resource para no atrapar errores de Supabase
  - Reglamento generado dinámicamente desde constantes, sin texto hardcodeado
  - Separación clara store/UI: todas las lecturas pasan por get_live_data()
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
ENABLE_REGISTRATION = get_bool_secret("ENABLE_REGISTRATION", True)
USERNAME_RE         = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9_. -]{3,40}$")

# ──────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
:root { --verde:#006341; --verde-osc:#004d32; --oro:#c8962c; }
html,body,[class*="css"] { font-family:'IBM Plex Sans',sans-serif; }
h1,h2,h3 { font-family:'Bebas Neue',sans-serif; letter-spacing:1px; }
.header-banner {
  background:linear-gradient(135deg,#006341 0%,#004d32 52%,#1a1a1a 100%);
  color:white; padding:22px 30px; border-radius:14px; margin-bottom:22px;
  border-bottom:4px solid var(--oro); box-shadow:0 8px 24px rgba(0,0,0,.12);
}
.header-banner h1 { color:white; margin:0; font-size:2.6rem; line-height:1; }
.header-banner p  { margin:6px 0 0; opacity:.88; font-size:.95rem; }
.metric-card {
  background:linear-gradient(135deg,var(--verde),var(--verde-osc));
  color:white; padding:14px 18px; border-radius:12px;
  border-left:4px solid var(--oro); margin-bottom:10px;
}
.metric-card .label { font-size:.72rem; opacity:.82; text-transform:uppercase; letter-spacing:1px; }
.metric-card .value { font-family:'Bebas Neue'; font-size:1.9rem; color:var(--oro); line-height:1.1; }
.badge { display:inline-block; color:white; font-size:.7rem; font-weight:700;
  padding:2px 9px; border-radius:20px; text-transform:uppercase;
  letter-spacing:.8px; white-space:nowrap; margin-right:4px; }
.b-group  { background:var(--verde); }
.b-open   { background:#2e7d32; }
.b-locked { background:#b71c1c; }
.b-result { background:#5d4037; }
.stTabs [data-baseweb="tab-list"] { gap:3px; background:#e8f5e9; border-radius:10px; padding:5px; }
.stTabs [data-baseweb="tab"]      { font-weight:700; border-radius:8px; }
.stTabs [aria-selected="true"]    { background:var(--verde)!important; color:white!important; }
details summary { font-weight:700; color:var(--verde); }
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
            self._save({"users": {}, "predictions": {}, "results": {}, "locks": {}, "audit_log": []})
        self._migrate()

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"users": {}, "predictions": {}, "results": {}, "locks": {}, "audit_log": []}

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
        for k in ("users", "predictions", "results", "locks"):
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

def get_live_data():
    """Una sola función de entrada para todos los datos vivos."""
    return (
        _cached_users(),
        _cached_all_preds(),
        _cached_results(),
        _cached_locks(),
    )

def invalidate_cache():
    """Llama después de cualquier escritura para que la UI refleje el cambio."""
    _cached_users.clear()
    _cached_all_preds.clear()
    _cached_results.clear()
    _cached_locks.clear()

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
GROUPS           = sorted(MATCHES["group"].dropna().unique().tolist()) if not MATCHES.empty else []
MATCH_IDX        = {r.match_id: r for r in MATCHES.itertuples(index=False)} if not MATCHES.empty else {}
CALENDAR_WARNINGS = validate_matches(MATCHES)
TOTAL_MATCHES    = len(MATCHES)

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
                "grupo":      getattr(match, "group", ""),
                "partido":    f"{getattr(match, 'home', '')} vs {getattr(match, 'away', '')}",
                "pronostico": f"{ph}-{pa}",
                "resultado":  result_txt,
                "puntos":     pts_val,
                "actualizado": pred.get("updated_at", ""),
            })
    return pd.DataFrame(rows)

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
<div class="header-banner">
  <h1>⚽ Quinela Mundial 2026</h1>
  <p>Plataforma oficial de pronósticos · Posgrado Instituto Mexicano del Petróleo</p>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────
USERS, ALL_PREDS, RESULTS, LOCKS = get_live_data()
STANDINGS = build_standings(USERS, ALL_PREDS, RESULTS)

with st.sidebar:
    st.markdown("### 🔑 Acceso")

    if not st.session_state.logged_in:
        tab_login, tab_reg = st.tabs(["Entrar", "Registrarse"])

        with tab_login:
            u_in = st.text_input("Usuario", key="login_u")
            p_in = st.text_input("Contraseña", type="password", key="login_p")
            if st.button("Iniciar sesión", use_container_width=True):
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
                if st.button("Crear cuenta", use_container_width=True):
                    ok, msg = register_user(u_r, p_r)
                    (st.success if ok else st.error)(msg)
    else:
        current_user = st.session_state.current_user
        st.success(f"✅ {current_user}")

        # ── Métricas personales (FIX: busca por _ukey consistentemente)
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

        st.markdown(f"""
        <div class="metric-card">
          <div class="label">Posición global</div>
          <div class="value">#{my_pos}</div>
        </div>
        <div class="metric-card">
          <div class="label">Mis puntos</div>
          <div class="value">{my_pts}</div>
        </div>
        <div class="metric-card">
          <div class="label">Pronosticados / Evaluados</div>
          <div class="value">{len(my_preds)} / {my_eval}</div>
        </div>
        """, unsafe_allow_html=True)

        # ── Barra de progreso ────────────────────────────────
        if TOTAL_MATCHES > 0:
            pct = len(my_preds) / TOTAL_MATCHES
            st.progress(pct, text=f"{len(my_preds)} de {TOTAL_MATCHES} partidos pronosticados")

        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state.logged_in    = False
            st.session_state.current_user = ""
            st.session_state.is_admin     = False
            st.rerun()

    st.divider()
    st.caption(
        f"🎯 Marcador exacto = **{POINTS_EXACT} pts**\n\n"
        f"✅ Resultado correcto = **{POINTS_RESULT} pt(s)**\n\n"
        "❌ Fallo = **0 pts**\n\n"
        "🔒 Los pronósticos se bloquean al inicio de cada partido."
    )
    sb_icon = "☁️" if isinstance(STORE, SupabaseStore) else "💾"
    st.caption(f"{sb_icon} Base de datos: **{STORE.name}** · 🕐 Zona: **{APP_TZ_NAME}**")
    if isinstance(STORE, LocalStore):
        st.info("Modo local activo. Configura Supabase en Secrets para producción.", icon="ℹ️")

# ──────────────────────────────────────────────────────────────
# PESTAÑAS
# ──────────────────────────────────────────────────────────────
tab_table, tab_preds, tab_results_tab, tab_rules_tab, tab_admin_tab = st.tabs([
    "🏆 Tabla General", "📝 Mis Pronósticos", "📊 Resultados", "📘 Reglamento", "⚙️ Administración"
])

# ════════════════════════════════════════
# 1 · TABLA GENERAL
# ════════════════════════════════════════
with tab_table:
    st.subheader("Clasificación global")

    if STANDINGS.empty:
        st.info("La tabla se activará cuando haya participantes y pronósticos registrados.")
    else:
        medals  = {1: "🥇", 2: "🥈", 3: "🥉"}
        max_pts = int(STANDINGS["Puntos"].max()) or 1

        display_df = STANDINGS.drop(columns=["_ukey"], errors="ignore").copy()
        display_df.insert(0, "Pos.", [
            f"{medals.get(i+1, '')} {i+1}" for i in range(len(display_df))
        ])
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Puntos":   st.column_config.ProgressColumn("Puntos", max_value=max_pts, format="%d"),
                "Promedio": st.column_config.NumberColumn(format="%.2f"),
                "Pos.":     st.column_config.TextColumn(width="small"),
            },
        )
        st.download_button(
            "⬇️ Descargar tabla CSV",
            data=display_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="tabla_quinela.csv",
            mime="text/csv",
        )

    c1, c2, c3, c4 = st.columns(4)
    n_bloqueados = (
        sum(1 for r in MATCHES.itertuples(index=False) if is_locked(r, LOCKS, RESULTS))
        if not MATCHES.empty else 0
    )
    c1.metric("Resultados cargados",  f"{len(RESULTS)} / {TOTAL_MATCHES}")
    c2.metric("Participantes",         len(USERS))
    c3.metric("Pronósticos totales",   sum(len(v) for v in ALL_PREDS.values()))
    c4.metric("Partidos bloqueados",   n_bloqueados)

# ════════════════════════════════════════
# 2 · MIS PRONÓSTICOS
# ════════════════════════════════════════
with tab_preds:
    st.subheader("Mis pronósticos")

    if not st.session_state.logged_in:
        st.warning("⚠️ Inicia sesión para registrar o modificar tus pronósticos.")
    elif MATCHES.empty:
        st.error("No se cargó el calendario de partidos.")
    else:
        current_user = st.session_state.current_user
        my_preds     = STORE.get_predictions(current_user)

        fc1, fc2, fc3 = st.columns([1, 2, 2])
        g_filter = fc1.selectbox("Grupo", ["Todos"] + GROUPS, key="f_group")
        t_filter = fc2.text_input("Buscar equipo", placeholder="México, Brasil…", key="f_text")
        s_filter = fc3.selectbox(
            "Estado", ["Todos", "Abiertos", "Bloqueados", "Con resultado"], key="f_status"
        )

        def match_visible(row):
            locked     = is_locked(row, LOCKS, RESULTS)
            has_result = row.match_id in RESULTS
            if g_filter != "Todos" and row.group != g_filter:
                return False
            if t_filter and t_filter.casefold() not in f"{row.home} {row.away}".casefold():
                return False
            if s_filter == "Abiertos"      and locked:         return False
            if s_filter == "Bloqueados"    and not locked:     return False
            if s_filter == "Con resultado" and not has_result: return False
            return True

        filtered = [r for r in MATCHES.itertuples(index=False) if match_visible(r)]

        if not filtered:
            st.info("Sin partidos que coincidan con los filtros.")
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
                                    b_status = ("b-result" if result else "b-locked" if locked else "b-open")
                                    b_text   = ("Resultado" if result else "Bloqueado" if locked else "Abierto")
                                    st.markdown(
                                        f'<span class="badge b-group">Grupo {row.group}</span>'
                                        f'<span class="badge {b_status}">{b_text}</span>',
                                        unsafe_allow_html=True,
                                    )
                                    st.markdown(f"**{row.home}** vs **{row.away}**")
                                    st.caption(f"📅 {fmt_kickoff(row)}  ·  📍 {row.venue}")

                                    if result:
                                        st.success(
                                            f"Resultado oficial: **{result['home_goals']} – {result['away_goals']}**"
                                        )
                                    if pred:
                                        line = f"Tu pronóstico: **{pred['home_goals']} – {pred['away_goals']}**"
                                        if result:
                                            pts = calc_pts(
                                                int(pred["home_goals"]), int(pred["away_goals"]),
                                                int(result["home_goals"]), int(result["away_goals"]),
                                            )
                                            line += f"  ·  {pts_label(pts)}"
                                        st.info(line)

                                    if locked:
                                        if not pred:
                                            st.caption("Sin pronóstico registrado antes del bloqueo.")
                                        continue

                                    with st.form(key=f"pf_{row.match_id}"):
                                        a, b = st.columns(2)
                                        dh = int(pred["home_goals"]) if pred else 0
                                        da = int(pred["away_goals"]) if pred else 0
                                        gh = a.number_input(row.home[:14], min_value=0, max_value=30, value=dh)
                                        ga = b.number_input(row.away[:14], min_value=0, max_value=30, value=da)
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
    st.subheader("Resultados oficiales")

    rc1, rc2 = st.columns([1, 3])
    rg       = rc1.selectbox("Filtrar por grupo", ["Todos"] + GROUPS, key="res_group")
    show_all = rc2.checkbox("Mostrar también partidos sin resultado", value=False)

    rows_res = []
    for row in MATCHES.itertuples(index=False):
        if rg != "Todos" and row.group != rg:
            continue
        res = RESULTS.get(row.match_id)
        if not res and not show_all:
            continue
        rows_res.append({
            "Grupo":     row.group,
            "ID":        row.match_id,
            "Local":     row.home,
            "Resultado": f"{res['home_goals']} – {res['away_goals']}" if res else "—",
            "Visitante": row.away,
            "Sede":      row.venue,
            "Fecha":     row.match_date,
        })
    if rows_res:
        st.dataframe(
            pd.DataFrame(rows_res),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Resultado": st.column_config.TextColumn(width="small"),
                "ID":        st.column_config.TextColumn(width="small"),
            },
        )
        st.caption(f"Mostrando {len(rows_res)} partidos · {len(RESULTS)} con resultado cargado.")
    else:
        st.info("Aún no hay resultados para este filtro.")

# ════════════════════════════════════════
# 4 · REGLAMENTO  (generado dinámicamente)
# ════════════════════════════════════════
with tab_rules_tab:
    st.subheader("Reglamento de la quinela")

    st.markdown(f"""
**Sistema de puntos**

| Criterio | Puntos |
|---|---:|
| Marcador exacto (p.ej. 2-1 = 2-1) | {POINTS_EXACT} |
| Resultado correcto sin marcador exacto (p.ej. pronóstico 2-1, resultado 3-0) | {POINTS_RESULT} |
| Pronóstico fallido | 0 |

**Desempates** (en orden de prioridad):

1. Mayor número de puntos totales
2. Mayor número de marcadores exactos ({POINTS_EXACT} pts)
3. Mayor número de resultados acertados ({POINTS_RESULT} pt)
4. Menor suma de diferencias absolutas de marcador
5. Mayor número de partidos pronosticados

**Bloqueo de pronósticos**

Cada partido se bloquea automáticamente al llegar su hora de inicio (`kickoff_at`).
Si la hora no está definida o hay un cambio operativo, el administrador puede activar el bloqueo manualmente.
Una vez bloqueado, el pronóstico ya no puede modificarse.

**Edición**

Puedes cambiar tu pronóstico cuantas veces quieras mientras el partido siga abierto.
Se guarda siempre el último valor confirmado.

**Participantes**

- Total de partidos: **{TOTAL_MATCHES}**
- Puntos máximos posibles: **{TOTAL_MATCHES * POINTS_EXACT}**
    """)

    if CALENDAR_WARNINGS:
        st.warning("⚠️ Revisión de calendario: " + " | ".join(CALENDAR_WARNINGS))

# ════════════════════════════════════════
# 5 · ADMINISTRACIÓN
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
        if st.button("Entrar como admin", use_container_width=True):
            if verify_admin(ap):
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")

    if st.session_state.is_admin:
        st.success("✅ Modo administrador activo")

        adm_res_tab, adm_lock_tab, adm_users_tab, adm_audit_tab, adm_export_tab = st.tabs([
            "Resultados", "Bloqueos manuales", "Participantes", "Auditoría", "Respaldo"
        ])

        # ── Resultados ────────────────────────────────────────
        with adm_res_tab:
            st.markdown("#### Publicar o corregir resultado oficial")
            st.caption("Publicar activa el bloqueo automáticamente en una sola operación.")

            if not MATCHES.empty:
                adm_g         = st.selectbox("Grupo", GROUPS, key="adm_group")
                group_matches = [r for r in MATCHES.itertuples(index=False) if r.group == adm_g]
                pendientes    = sum(1 for r in group_matches if r.match_id not in RESULTS)
                st.info(f"Partidos sin resultado en Grupo {adm_g}: **{pendientes}**")

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

                if st.button("📥 Publicar resultado", use_container_width=True, type="primary"):
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
                    if st.button("🗑️ Eliminar resultado", type="secondary"):
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
            blk_g       = st.selectbox("Grupo", GROUPS, key="blk_group")
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
            if st.button("Guardar bloqueo", use_container_width=True):
                STORE.set_lock(blk_row.match_id, new_lock)
                STORE.append_audit(
                    st.session_state.current_user or "admin", "manual_lock_updated",
                    {"match_id": blk_row.match_id, "locked": bool(new_lock)},
                )
                invalidate_cache()
                st.success("Bloqueo actualizado.")
                st.rerun()

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
                if st.button("🔑 Aplicar nueva contraseña", use_container_width=True):
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
            )
            st.download_button(
                "⬇️ Descargar calendario CSV",
                data=MATCHES.to_csv(index=False).encode("utf-8"),
                file_name="matches_2026.csv",
                mime="text/csv",
                use_container_width=True,
            )

        if st.button("Salir de administración", type="secondary"):
            st.session_state.is_admin = False
            st.rerun()
