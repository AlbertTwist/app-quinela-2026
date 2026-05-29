"""
Quinela Mundial 2026 · Posgrado IMP
=====================================
v3 — Mejoras sobre versión anterior:
  - CSV con nombres en español y kickoff_at completo → bloqueo automático funciona
  - supabase es opcional; requirements.txt base no lo incluye
  - Operaciones Supabase con manejo de error explícito (resultado + lock atómico)
  - data/.gitkeep garantiza que el directorio existe en el repo
  - Paginación por jornada en "Mis Pronósticos" (expanders por fecha)
  - Tabla de posiciones con barra de progreso visual y medallas top-3
  - Panel admin con contador de pendientes y vista previa de bloqueos
  - Sidebar muestra posición global del usuario
  - Validación de kickoff_at en zona horaria local sin depender de pytz
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

# Supabase es opcional
try:
    from supabase import create_client as _sb_create
except Exception:
    _sb_create = None  # type: ignore[assignment]

# ──────────────────────────────────────────────────────────────
# CONFIGURACIÓN GENERAL
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Quinela Mundial 2026 · IMP",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT = Path(__file__).resolve().parent
MATCHES_FILE = ROOT / "matches_2026.csv"
LOCAL_DATA_FILE = ROOT / "data" / "quinela_data.json"


def get_secret(name: str, default: str = "") -> str:
    val = None
    try:
        val = st.secrets.get(name)  # type: ignore[attr-defined]
    except Exception:
        pass
    if val is None:
        val = os.environ.get(name, default)
    return str(val) if val is not None else default


APP_TZ_NAME   = get_secret("APP_TZ", "America/Mexico_City")
try:
    APP_TZ = ZoneInfo(APP_TZ_NAME)
except Exception:
    APP_TZ_NAME = "America/Mexico_City"
    APP_TZ = ZoneInfo(APP_TZ_NAME)

ADMIN_PASSWORD      = get_secret("ADMIN_PASSWORD", "")
ADMIN_PASSWORD_HASH = get_secret("ADMIN_PASSWORD_HASH", "")
SUPABASE_URL        = get_secret("SUPABASE_URL", "")
SUPABASE_KEY        = get_secret("SUPABASE_SERVICE_ROLE_KEY", "") or get_secret("SUPABASE_KEY", "")

USERNAME_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9_. -]{3,40}$")

# ──────────────────────────────────────────────────────────────
# ESTILO
# ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
:root {
  --verde:#006341; --verde-osc:#004d32; --oro:#c8962c;
  --claro:#f5f0e8; --tinta:#1a1a1a;
}
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

/* badges */
.badge {
  display:inline-block; color:white; font-size:.7rem; font-weight:700;
  padding:2px 9px; border-radius:20px; text-transform:uppercase;
  letter-spacing:.8px; white-space:nowrap; margin-right:4px;
}
.b-group   { background:var(--verde); }
.b-open    { background:#2e7d32; }
.b-locked  { background:#b71c1c; }
.b-result  { background:#5d4037; }

/* tabla posiciones */
.pos-medal { font-size:1.2rem; }

.stTabs [data-baseweb="tab-list"] {
  gap:3px; background:#e8f5e9; border-radius:10px; padding:5px;
}
.stTabs [data-baseweb="tab"]          { font-weight:700; border-radius:8px; }
.stTabs [aria-selected="true"]        { background:var(--verde)!important; color:white!important; }

/* expander de jornada */
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
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iters)
    return f"pbkdf2_sha256${iters}${salt.hex()}${digest.hex()}"

def verify_password(pw: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, it_s, salt_hex, digest_hex = stored.split("$", 3)
            digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), int(it_s)).hex()
            return hmac.compare_digest(digest, digest_hex)
        except Exception:
            return False
    # hash SHA256 legado (64 hex)
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
# ALMACENAMIENTO
# ──────────────────────────────────────────────────────────────
class LocalStore:
    name = "JSON local"

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"users": {}, "predictions": {}, "results": {}, "locks": {}})
        self._migrate()

    # ── I/O ──────────────────────────────────────────────────
    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"users": {}, "predictions": {}, "results": {}, "locks": {}}

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

    # ── Migración de formatos anteriores ─────────────────────
    def _migrate(self) -> None:
        data = self._load()
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
            data["predictions"] = {user_key(u): {mid: to_score(s) for mid, s in preds.items()}
                                    for u, preds in old.items()}
            changed = True

        if "resultados" in data:
            data["results"] = {mid: to_score(s) for mid, s in data.pop("resultados", {}).items()}
            changed = True

        for k in ("users", "predictions", "results", "locks"):
            data.setdefault(k, {})

        if changed:
            self._save(data)

    # ── Usuarios ─────────────────────────────────────────────
    def list_users(self) -> list[dict]:
        return list(self._load()["users"].values())

    def get_user(self, username: str) -> dict | None:
        return self._load()["users"].get(user_key(username))

    def create_user(self, username: str, pw_hash: str) -> None:
        data = self._load()
        k = user_key(username)
        data["users"][k] = {
            "username": normalize_username(username),
            "password_hash": pw_hash,
            "created_at": datetime.now(APP_TZ).isoformat(timespec="seconds"),
        }
        data["predictions"].setdefault(k, {})
        self._save(data)

    def update_user_hash(self, username: str, pw_hash: str) -> None:
        data = self._load()
        k = user_key(username)
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
        k = user_key(username)
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
        """Guarda resultado y activa bloqueo en una sola escritura."""
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

    def export_all(self) -> dict:
        return self._load()


class SupabaseStore:
    name = "Supabase"

    def __init__(self, url: str, key: str):
        if _sb_create is None:
            raise RuntimeError(
                "supabase no está instalado. Ejecuta: pip install supabase\n"
                "O agrega supabase>=2.6 a requirements.txt."
            )
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
            "username": user_key(username),
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
            "username": user_key(username), "match_id": match_id,
            "home_goals": int(home), "away_goals": int(away),
            "updated_at": datetime.now(APP_TZ).isoformat(),
        }, on_conflict="username,match_id").execute()

    def list_results(self) -> dict:
        rows = (self.client.table("quinela_results")
                .select("match_id,home_goals,away_goals,updated_at").execute().data or [])
        return {r["match_id"]: r for r in rows}

    def upsert_result(self, match_id: str, home: int, away: int) -> None:
        self.client.table("quinela_results").upsert({
            "match_id": match_id,
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
        """Intenta guardar resultado y bloqueo. Reporta error si alguno falla."""
        try:
            self.upsert_result(match_id, home, away)
        except Exception as exc:
            return False, f"Error al guardar resultado: {exc}"
        try:
            self.set_lock(match_id, True)
        except Exception as exc:
            # El resultado YA se guardó; el bloqueo falló. Avisamos pero no revertimos.
            return False, (
                f"Resultado guardado ✓, pero el bloqueo falló: {exc}\n"
                "Usa el panel de Bloqueos para activarlo manualmente."
            )
        return True, "ok"

    def export_all(self) -> dict:
        return {
            "users": self.list_users(),
            "predictions": self.list_all_predictions(),
            "results": self.list_results(),
            "locks": self.list_locks(),
            "exported_at": datetime.now(APP_TZ).isoformat(),
        }


@st.cache_resource(show_spinner=False)
def get_store():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            return SupabaseStore(SUPABASE_URL, SUPABASE_KEY)
        except Exception as exc:
            st.sidebar.warning(f"Supabase no disponible ({exc}). Usando almacenamiento local.")
    return LocalStore(LOCAL_DATA_FILE)


STORE = get_store()

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
        st.error(f"matches_2026.csv falta columnas: {', '.join(sorted(missing))}")
        return pd.DataFrame()
    df["match_id"] = df["match_id"].astype(str)
    df["group"] = df["group"].astype(str)
    return df


MATCHES   = load_matches()
GROUPS    = sorted(MATCHES["group"].dropna().unique().tolist()) if not MATCHES.empty else []
MATCH_IDX = {r.match_id: r for r in MATCHES.itertuples(index=False)} if not MATCHES.empty else {}

# Jornadas por fecha de partido
if not MATCHES.empty:
    DATE_GROUPS = MATCHES.groupby("match_date")["match_id"].apply(list).to_dict()
else:
    DATE_GROUPS = {}

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
        return 3
    return 1 if ((ph > pa) - (ph < pa)) == ((rh > ra) - (rh < ra)) else 0


def pts_label(pts: int) -> str:
    return {3: "🎯 Exacto · +3", 1: "✅ Resultado · +1", 0: "❌ Sin puntos"}[pts]


def build_standings(users, all_preds, results) -> pd.DataFrame:
    rows = []
    for u in users:
        uname = u["username"]
        display = u.get("display_name") or uname
        preds = all_preds.get(uname, {})
        pts = exactos = correctos = evaluados = pronosticados = dif = 0
        for mid, pred in preds.items():
            pronosticados += 1
            res = results.get(mid)
            if not res:
                continue
            evaluados += 1
            ph, pa = int(pred["home_goals"]), int(pred["away_goals"])
            rh, ra = int(res["home_goals"]), int(res["away_goals"])
            p = calc_pts(ph, pa, rh, ra)
            pts += p
            exactos   += int(p == 3)
            correctos += int(p >= 1)
            dif       += abs(ph - rh) + abs(pa - ra)
        rows.append({
            "Usuario": display,
            "Puntos": pts,
            "Exactos 🎯": exactos,
            "Acertados ✅": correctos,
            "Dif. marcador": dif,
            "Evaluados": evaluados,
            "Pronosticados": pronosticados,
            "Promedio": round(pts / evaluados, 2) if evaluados else 0.0,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(
        ["Puntos", "Exactos 🎯", "Acertados ✅", "Dif. marcador", "Pronosticados"],
        ascending=[False, False, False, True, False],
    ).reset_index(drop=True)


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
        return False, "Ese usuario ya existe."
    STORE.create_user(username, make_password_hash(pw))
    return True, "Cuenta creada. Ahora inicia sesión."


def login_user(username: str, pw: str) -> tuple[bool, str]:
    username = normalize_username(username)
    record = STORE.get_user(username)
    if not record or not verify_password(pw, record.get("password_hash", "")):
        return False, "Credenciales incorrectas."
    # Migra hash legado en el primer login exitoso
    if not record["password_hash"].startswith("pbkdf2_sha256$"):
        STORE.update_user_hash(username, make_password_hash(pw))
    st.session_state.logged_in    = True
    st.session_state.current_user = record["username"]
    return True, "Sesión iniciada."


# ──────────────────────────────────────────────────────────────
# ESTADO DE SESIÓN
# ──────────────────────────────────────────────────────────────
for _k, _d in {"logged_in": False, "current_user": "", "is_admin": False}.items():
    st.session_state.setdefault(_k, _d)

# Datos vivos (sin cache: siempre reflejan el estado actual del store)
USERS      = STORE.list_users()
ALL_PREDS  = STORE.list_all_predictions()
RESULTS    = STORE.list_results()
LOCKS      = STORE.list_locks()
STANDINGS  = build_standings(USERS, ALL_PREDS, RESULTS)

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
            u_r = st.text_input("Nombre de usuario", placeholder="Nombre Apellido", key="reg_u")
            p_r = st.text_input("Contraseña (mín. 8)", type="password", key="reg_p")
            if st.button("Crear cuenta", use_container_width=True):
                ok, msg = register_user(u_r, p_r)
                (st.success if ok else st.error)(msg)

    else:
        st.success(f"✅ {st.session_state.current_user}")

        my_preds   = STORE.get_predictions(st.session_state.current_user)
        my_ukey    = user_key(st.session_state.current_user)
        my_row_df  = STANDINGS[STANDINGS["Usuario"].str.casefold() == my_ukey] if not STANDINGS.empty else pd.DataFrame()
        my_pts     = int(my_row_df.iloc[0]["Puntos"])    if not my_row_df.empty else 0
        my_eval    = int(my_row_df.iloc[0]["Evaluados"]) if not my_row_df.empty else 0
        my_pos     = my_row_df.index[0] + 1              if not my_row_df.empty else "-"

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
          <div class="label">Pronosticados / evaluados</div>
          <div class="value">{len(my_preds)} / {my_eval}</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Cerrar sesión", use_container_width=True):
            for _k in ("logged_in", "current_user", "is_admin"):
                st.session_state[_k] = False if _k != "current_user" else ""
            st.rerun()

    st.divider()
    st.caption(
        "🎯 Marcador exacto = **3 pts**\n\n"
        "✅ Resultado correcto = **1 pt**\n\n"
        "❌ Fallo = **0 pts**\n\n"
        "🔒 Los pronósticos se bloquean al inicio de cada partido."
    )
    sb_icon = "☁️" if isinstance(STORE, SupabaseStore) else "💾"
    st.caption(f"{sb_icon} Base de datos: **{STORE.name}** · 🕐 Zona: **{APP_TZ_NAME}**")
    if isinstance(STORE, LocalStore):
        st.info("Modo local activo. Para producción configura Supabase en los Secrets.", icon="ℹ️")

# ──────────────────────────────────────────────────────────────
# PESTAÑAS
# ──────────────────────────────────────────────────────────────
tab_table, tab_preds, tab_results_tab, tab_admin_tab = st.tabs([
    "🏆 Tabla General", "📝 Mis Pronósticos", "📊 Resultados", "⚙️ Administración"
])

# ════════════════════════════════════════
# 1 · TABLA GENERAL
# ════════════════════════════════════════
with tab_table:
    st.subheader("Clasificación global")

    if STANDINGS.empty:
        st.info("La tabla se activará cuando haya participantes y pronósticos.")
    else:
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        max_pts = STANDINGS["Puntos"].max() or 1

        display_df = STANDINGS.copy()
        display_df.insert(0, "Pos.", [
            f"{medals.get(i+1, '')} {i+1}" for i in range(len(display_df))
        ])
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Puntos":      st.column_config.ProgressColumn("Puntos", max_value=int(max_pts), format="%d"),
                "Promedio":    st.column_config.NumberColumn(format="%.2f"),
                "Pos.":        st.column_config.TextColumn(width="small"),
            },
        )

    c1, c2, c3, c4 = st.columns(4)
    n_bloqueados = sum(1 for r in MATCHES.itertuples(index=False) if is_locked(r, LOCKS, RESULTS)) if not MATCHES.empty else 0
    c1.metric("Resultados cargados",  f"{len(RESULTS)} / {len(MATCHES)}")
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

        # ── Filtros ──────────────────────────────────────────
        fc1, fc2, fc3 = st.columns([1, 2, 2])
        g_filter = fc1.selectbox("Grupo", ["Todos"] + GROUPS, key="f_group")
        t_filter = fc2.text_input("Buscar equipo", placeholder="México, Brasil…", key="f_text")
        s_filter = fc3.selectbox("Estado", ["Todos", "Abiertos", "Bloqueados", "Con resultado"], key="f_status")

        def match_visible(row):
            locked     = is_locked(row, LOCKS, RESULTS)
            has_result = row.match_id in RESULTS
            if g_filter != "Todos" and row.group != g_filter:
                return False
            if t_filter and t_filter.casefold() not in f"{row.home} {row.away}".casefold():
                return False
            if s_filter == "Abiertos"       and locked:         return False
            if s_filter == "Bloqueados"     and not locked:     return False
            if s_filter == "Con resultado"  and not has_result: return False
            return True

        filtered = [r for r in MATCHES.itertuples(index=False) if match_visible(r)]

        if not filtered:
            st.info("Sin partidos que coincidan con los filtros.")
        else:
            # ── Agrupar por fecha (jornada) ───────────────────
            by_date: dict[str, list] = {}
            for row in filtered:
                by_date.setdefault(row.match_date, []).append(row)

            for date_str, matches_day in sorted(by_date.items()):
                # Contar abiertos en la jornada
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
                                    # Badges
                                    b_status = ("b-result" if result
                                                else "b-locked" if locked else "b-open")
                                    b_text   = ("Resultado" if result
                                                else "Bloqueado" if locked else "Abierto")
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
                                            st.caption("Sin pronóstico antes del bloqueo.")
                                        continue

                                    with st.form(key=f"pf_{row.match_id}"):
                                        a, b = st.columns(2)
                                        dh = int(pred["home_goals"]) if pred else 0
                                        da = int(pred["away_goals"]) if pred else 0
                                        gh = a.number_input(row.home[:14], min_value=0, max_value=30, value=dh)
                                        ga = b.number_input(row.away[:14], min_value=0, max_value=30, value=da)
                                        if st.form_submit_button("💾 Guardar", use_container_width=True):
                                            # Revalidar bloqueo al momento exacto del submit
                                            fresh_res   = STORE.list_results()
                                            fresh_locks = STORE.list_locks()
                                            if is_locked(row, fresh_locks, fresh_res):
                                                st.error("Partido bloqueado justo al enviar. No se guardó.")
                                            else:
                                                STORE.upsert_prediction(current_user, row.match_id, int(gh), int(ga))
                                                st.success("Pronóstico guardado ✓")
                                                st.rerun()

# ════════════════════════════════════════
# 3 · RESULTADOS
# ════════════════════════════════════════
with tab_results_tab:
    st.subheader("Resultados oficiales")
    rg = st.selectbox("Filtrar por grupo", ["Todos"] + GROUPS, key="res_group")
    rows_res = []
    for row in MATCHES.itertuples(index=False):
        if rg != "Todos" and row.group != rg:
            continue
        res = RESULTS.get(row.match_id)
        if not res:
            continue
        rows_res.append({
            "Grupo":      row.group,
            "Partido":    f"{row.home} vs {row.away}",
            "Resultado":  f"{res['home_goals']} – {res['away_goals']}",
            "Sede":       row.venue,
        })
    if rows_res:
        st.dataframe(pd.DataFrame(rows_res), use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay resultados para este filtro.")

# ════════════════════════════════════════
# 4 · ADMINISTRACIÓN
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

        adm_res_tab, adm_lock_tab, adm_export_tab = st.tabs(
            ["Resultados", "Bloqueos manuales", "Respaldo"]
        )

        # ── Resultados ────────────────────────────────────────
        with adm_res_tab:
            st.markdown("#### Publicar o corregir resultado oficial")
            st.caption("Publicar activa el bloqueo automáticamente. Ambas operaciones son atómicas.")

            if MATCHES.empty:
                st.error("No hay calendario cargado.")
            else:
                adm_g = st.selectbox("Grupo", GROUPS, key="adm_group")
                group_matches = [r for r in MATCHES.itertuples(index=False) if r.group == adm_g]

                # Contador de partidos pendientes de resultado en el grupo
                pendientes = sum(1 for r in group_matches if r.match_id not in RESULTS)
                st.info(f"Partidos sin resultado en Grupo {adm_g}: **{pendientes}**")

                adm_idx = st.selectbox(
                    "Partido",
                    range(len(group_matches)),
                    format_func=lambda i: (
                        f"{group_matches[i].match_id} · {group_matches[i].home} vs "
                        f"{group_matches[i].away}"
                        + (" ✅" if group_matches[i].match_id in RESULTS else "")
                    ),
                    key="adm_match",
                )
                sel = group_matches[adm_idx]
                existing = RESULTS.get(sel.match_id, {})
                if existing:
                    st.warning(
                        f"Ya existe resultado: **{existing['home_goals']} – {existing['away_goals']}**. "
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
                        st.success(f"✅ Resultado publicado: {sel.home} **{rh}** – **{ra}** {sel.away}")
                        st.rerun()
                    else:
                        st.error(f"Error: {msg}")

                st.divider()
                st.markdown("#### Eliminar resultado")
                if RESULTS:
                    del_id = st.selectbox(
                        "Resultado a eliminar",
                        list(RESULTS.keys()),
                        format_func=lambda mid: (
                            f"{mid} · {MATCH_IDX[mid].home} vs {MATCH_IDX[mid].away}"
                            if mid in MATCH_IDX else mid
                        ),
                        key="del_id",
                    )
                    if st.button("🗑️ Eliminar resultado", type="secondary"):
                        STORE.delete_result(del_id)
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

            blk_g = st.selectbox("Grupo", GROUPS, key="blk_group")
            blk_matches = [r for r in MATCHES.itertuples(index=False) if r.group == blk_g]

            # Vista de estado de bloqueos del grupo
            blk_rows = []
            for r in blk_matches:
                auto = parse_kickoff(getattr(r, "kickoff_at", ""))
                auto_bloq = bool(auto and datetime.now(APP_TZ) >= auto)
                blk_rows.append({
                    "ID": r.match_id,
                    "Partido": f"{r.home} vs {r.away}",
                    "Auto (kickoff)": "🔒" if auto_bloq else ("⏳" if auto else "—"),
                    "Manual": "🔒" if LOCKS.get(r.match_id) else "🔓",
                    "Resultado": "✅" if r.match_id in RESULTS else "—",
                })
            st.dataframe(pd.DataFrame(blk_rows), hide_index=True, use_container_width=True)

            blk_idx = st.selectbox(
                "Partido a bloquear/desbloquear",
                range(len(blk_matches)),
                format_func=lambda i: f"{blk_matches[i].match_id} · {blk_matches[i].home} vs {blk_matches[i].away}",
                key="blk_idx",
            )
            blk_row = blk_matches[blk_idx]
            cur_lock = bool(LOCKS.get(blk_row.match_id, False))
            new_lock = st.toggle("Bloqueo manual activado", value=cur_lock, key="blk_toggle")
            if st.button("Guardar bloqueo", use_container_width=True):
                STORE.set_lock(blk_row.match_id, new_lock)
                st.success("Bloqueo actualizado.")
                st.rerun()

        # ── Respaldo ─────────────────────────────────────────
        with adm_export_tab:
            st.markdown("#### Respaldo de datos")
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
