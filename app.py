"""
Quinela Mundial 2026 · Posgrado IMP
Versión robusta para GitHub + Streamlit Community Cloud.

Mejoras principales:
- Persistencia real con Supabase si se configuran secretos.
- Respaldo local JSON solo para desarrollo/pruebas.
- Hash de contraseñas con PBKDF2 + salt.
- Bloqueo automático por kickoff_at y bloqueo manual de admin.
- Sin st.stop() dentro de pestañas.
- IDs estables por partido en lugar de claves basadas en nombres.
- Fixture externo en CSV para poder corregir calendario sin tocar el código.
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

try:
    from supabase import create_client
except Exception:  # pragma: no cover - fallback local si no está instalado/configurado
    create_client = None

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
    """Lee secretos de Streamlit Cloud, .streamlit/secrets.toml o variables de entorno."""
    value = None
    try:
        value = st.secrets.get(name)  # type: ignore[attr-defined]
    except Exception:
        value = None
    if value is None:
        value = os.environ.get(name, default)
    return str(value) if value is not None else default


APP_TZ_NAME = get_secret("APP_TZ", "America/Mexico_City")
try:
    APP_TZ = ZoneInfo(APP_TZ_NAME)
except Exception:
    APP_TZ_NAME = "America/Mexico_City"
    APP_TZ = ZoneInfo(APP_TZ_NAME)

ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", "")
ADMIN_PASSWORD_HASH = get_secret("ADMIN_PASSWORD_HASH", "")
SUPABASE_URL = get_secret("SUPABASE_URL", "")
SUPABASE_KEY = get_secret("SUPABASE_SERVICE_ROLE_KEY", "") or get_secret("SUPABASE_KEY", "")

USERNAME_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9_. -]{3,40}$")

# ──────────────────────────────────────────────────────────────
# ESTILO
# ──────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
:root {
  --imp-verde:#006341; --imp-verde-oscuro:#004d32; --imp-oro:#c8962c;
  --imp-claro:#f5f0e8; --imp-tinta:#1a1a1a;
}
html, body, [class*="css"] { font-family:'IBM Plex Sans', sans-serif; }
h1, h2, h3 { font-family:'Bebas Neue', sans-serif; letter-spacing:1px; }
.header-banner {
  background: linear-gradient(135deg, #006341 0%, #004d32 52%, #1a1a1a 100%);
  color:white; padding:22px 30px; border-radius:14px; margin-bottom:22px;
  border-bottom:4px solid var(--imp-oro); box-shadow:0 10px 24px rgba(0,0,0,.10);
}
.header-banner h1 { color:white; margin:0; font-size:2.55rem; line-height:1; }
.header-banner p { margin:7px 0 0; opacity:.88; font-size:.95rem; }
.group-badge, .locked-badge, .open-badge, .result-badge {
  display:inline-block; color:white; font-size:.72rem; font-weight:700; padding:3px 9px;
  border-radius:20px; text-transform:uppercase; letter-spacing:.8px; white-space:nowrap;
}
.group-badge { background:var(--imp-verde); }
.locked-badge { background:#b71c1c; }
.open-badge { background:#2e7d32; }
.result-badge { background:#6a4a00; }
.metric-card {
  background:linear-gradient(135deg, var(--imp-verde), var(--imp-verde-oscuro));
  color:white; padding:16px 18px; border-radius:12px; border-left:4px solid var(--imp-oro);
  margin-bottom:10px;
}
.metric-card .label { font-size:.72rem; opacity:.82; text-transform:uppercase; letter-spacing:1px; }
.metric-card .value { font-family:'Bebas Neue'; font-size:2rem; color:var(--imp-oro); line-height:1.05; }
.small-muted { color:#666; font-size:.82rem; }
.stTabs [data-baseweb="tab-list"] { gap:3px; background:#f0f2f6; border-radius:10px; padding:5px; }
.stTabs [data-baseweb="tab"] { font-weight:700; border-radius:8px; }
</style>
""",
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────
# SEGURIDAD / HASHING
# ──────────────────────────────────────────────────────────────

def normalize_username(username: str) -> str:
    return " ".join(username.strip().split())


def user_key(username: str) -> str:
    return normalize_username(username).casefold()


def make_password_hash(password: str, iterations: int = 260_000) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Valida PBKDF2. Mantiene compatibilidad con hashes SHA256 legados de 64 hex."""
    if not stored_hash:
        return False
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, it_s, salt_hex, digest_hex = stored_hash.split("$", 3)
            digest = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(it_s)
            ).hex()
            return hmac.compare_digest(digest, digest_hex)
        except Exception:
            return False
    if re.fullmatch(r"[a-fA-F0-9]{64}", stored_hash):
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy, stored_hash)
    return False


def verify_admin_password(candidate: str) -> bool:
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

@dataclass
class UserRecord:
    username: str
    password_hash: str
    created_at: str | None = None


class LocalStore:
    """Respaldo local para desarrollo. En Streamlit Cloud no debe ser el backend definitivo."""

    name = "JSON local"

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"users": {}, "predictions": {}, "results": {}, "locks": {}})
        self._migrate_if_needed()

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"users": {}, "predictions": {}, "results": {}, "locks": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="quinela_", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)

    def _migrate_if_needed(self) -> None:
        data = self._load()
        changed = False

        def convert_score(payload: dict[str, Any]) -> dict[str, Any]:
            if "home_goals" in payload and "away_goals" in payload:
                return payload
            if "L" in payload and "V" in payload:
                return {
                    "home_goals": int(payload.get("L", 0)),
                    "away_goals": int(payload.get("V", 0)),
                    "updated_at": payload.get("updated_at"),
                }
            return payload

        if "usuarios" in data:
            users = data.setdefault("users", {})
            for username, pw_hash in data.get("usuarios", {}).items():
                key = user_key(username)
                users[key] = {"username": key, "display_name": normalize_username(username), "password_hash": pw_hash, "created_at": None}
            data.pop("usuarios", None)
            changed = True

        if "pronosticos" in data:
            old_preds = data.pop("pronosticos", {})
            converted: dict[str, dict[str, Any]] = {}
            for username, preds in old_preds.items():
                converted[user_key(username)] = {mid: convert_score(score) for mid, score in preds.items()}
            data["predictions"] = converted
            changed = True

        if "resultados" in data:
            old_results = data.pop("resultados", {})
            data["results"] = {mid: convert_score(score) for mid, score in old_results.items()}
            changed = True

        data.setdefault("users", {})
        data.setdefault("predictions", {})
        data.setdefault("results", {})
        data.setdefault("locks", {})

        # Normaliza estructuras parcialmente migradas.
        normalized_preds: dict[str, dict[str, Any]] = {}
        for username, preds in data.get("predictions", {}).items():
            normalized_preds[user_key(username)] = {mid: convert_score(score) for mid, score in preds.items()}
        if normalized_preds != data.get("predictions", {}):
            data["predictions"] = normalized_preds
            changed = True

        normalized_results = {mid: convert_score(score) for mid, score in data.get("results", {}).items()}
        if normalized_results != data.get("results", {}):
            data["results"] = normalized_results
            changed = True

        if changed:
            self._save(data)

    def list_users(self) -> list[dict[str, Any]]:
        data = self._load()
        return list(data.get("users", {}).values())

    def get_user(self, username: str) -> dict[str, Any] | None:
        return self._load().get("users", {}).get(user_key(username))

    def create_user(self, username: str, password_hash: str) -> None:
        data = self._load()
        key = user_key(username)
        data["users"][key] = {
            "username": normalize_username(username),
            "password_hash": password_hash,
            "created_at": datetime.now(APP_TZ).isoformat(timespec="seconds"),
        }
        data["predictions"].setdefault(key, {})
        self._save(data)

    def update_user_hash(self, username: str, password_hash: str) -> None:
        data = self._load()
        key = user_key(username)
        if key in data.get("users", {}):
            data["users"][key]["password_hash"] = password_hash
            self._save(data)

    def get_predictions(self, username: str) -> dict[str, dict[str, int]]:
        return self._load().get("predictions", {}).get(user_key(username), {})

    def list_all_predictions(self) -> dict[str, dict[str, dict[str, int]]]:
        return self._load().get("predictions", {})

    def upsert_prediction(self, username: str, match_id: str, home_goals: int, away_goals: int) -> None:
        data = self._load()
        key = user_key(username)
        data.setdefault("predictions", {}).setdefault(key, {})[match_id] = {
            "home_goals": int(home_goals),
            "away_goals": int(away_goals),
            "updated_at": datetime.now(APP_TZ).isoformat(timespec="seconds"),
        }
        self._save(data)

    def list_results(self) -> dict[str, dict[str, int]]:
        return self._load().get("results", {})

    def upsert_result(self, match_id: str, home_goals: int, away_goals: int) -> None:
        data = self._load()
        data.setdefault("results", {})[match_id] = {
            "home_goals": int(home_goals),
            "away_goals": int(away_goals),
            "updated_at": datetime.now(APP_TZ).isoformat(timespec="seconds"),
        }
        self._save(data)

    def delete_result(self, match_id: str) -> None:
        data = self._load()
        data.setdefault("results", {}).pop(match_id, None)
        self._save(data)

    def list_locks(self) -> dict[str, bool]:
        return self._load().get("locks", {})

    def set_lock(self, match_id: str, locked: bool) -> None:
        data = self._load()
        data.setdefault("locks", {})[match_id] = bool(locked)
        self._save(data)

    def export_all(self) -> dict[str, Any]:
        return self._load()


class SupabaseStore:
    name = "Supabase"

    def __init__(self, url: str, key: str):
        if create_client is None:
            raise RuntimeError("No se pudo importar supabase. Revisa requirements.txt.")
        self.client = create_client(url, key)

    def list_users(self) -> list[dict[str, Any]]:
        res = self.client.table("quinela_users").select("username,display_name,password_hash,created_at").execute()
        return res.data or []

    def get_user(self, username: str) -> dict[str, Any] | None:
        res = (
            self.client.table("quinela_users")
            .select("username,display_name,password_hash,created_at")
            .eq("username", user_key(username))
            .limit(1)
            .execute()
        )
        return (res.data or [None])[0]

    def create_user(self, username: str, password_hash: str) -> None:
        self.client.table("quinela_users").insert(
            {"username": user_key(username), "display_name": normalize_username(username), "password_hash": password_hash}
        ).execute()

    def update_user_hash(self, username: str, password_hash: str) -> None:
        self.client.table("quinela_users").update({"password_hash": password_hash}).eq(
            "username", user_key(username)
        ).execute()

    def get_predictions(self, username: str) -> dict[str, dict[str, int]]:
        res = (
            self.client.table("quinela_predictions")
            .select("match_id,home_goals,away_goals,updated_at")
            .eq("username", user_key(username))
            .execute()
        )
        return {r["match_id"]: r for r in (res.data or [])}

    def list_all_predictions(self) -> dict[str, dict[str, dict[str, int]]]:
        res = self.client.table("quinela_predictions").select("username,match_id,home_goals,away_goals,updated_at").execute()
        out: dict[str, dict[str, dict[str, int]]] = {}
        for r in res.data or []:
            out.setdefault(r["username"], {})[r["match_id"]] = r
        return out

    def upsert_prediction(self, username: str, match_id: str, home_goals: int, away_goals: int) -> None:
        self.client.table("quinela_predictions").upsert(
            {
                "username": user_key(username),
                "match_id": match_id,
                "home_goals": int(home_goals),
                "away_goals": int(away_goals),
                "updated_at": datetime.now(APP_TZ).isoformat(),
            },
            on_conflict="username,match_id",
        ).execute()

    def list_results(self) -> dict[str, dict[str, int]]:
        res = self.client.table("quinela_results").select("match_id,home_goals,away_goals,updated_at").execute()
        return {r["match_id"]: r for r in (res.data or [])}

    def upsert_result(self, match_id: str, home_goals: int, away_goals: int) -> None:
        self.client.table("quinela_results").upsert(
            {
                "match_id": match_id,
                "home_goals": int(home_goals),
                "away_goals": int(away_goals),
                "updated_at": datetime.now(APP_TZ).isoformat(),
            },
            on_conflict="match_id",
        ).execute()

    def delete_result(self, match_id: str) -> None:
        self.client.table("quinela_results").delete().eq("match_id", match_id).execute()

    def list_locks(self) -> dict[str, bool]:
        res = self.client.table("quinela_locks").select("match_id,locked").execute()
        return {r["match_id"]: bool(r.get("locked")) for r in (res.data or [])}

    def set_lock(self, match_id: str, locked: bool) -> None:
        self.client.table("quinela_locks").upsert(
            {"match_id": match_id, "locked": bool(locked), "updated_at": datetime.now(APP_TZ).isoformat()},
            on_conflict="match_id",
        ).execute()

    def export_all(self) -> dict[str, Any]:
        return {
            "users": self.list_users(),
            "predictions": self.list_all_predictions(),
            "results": self.list_results(),
            "locks": self.list_locks(),
            "exported_at": datetime.now(APP_TZ).isoformat(),
        }


def get_store() -> LocalStore | SupabaseStore:
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            return SupabaseStore(SUPABASE_URL, SUPABASE_KEY)
        except Exception as exc:
            st.sidebar.error(f"Supabase no disponible: {exc}")
    return LocalStore(LOCAL_DATA_FILE)


STORE = get_store()

# ──────────────────────────────────────────────────────────────
# FIXTURE Y LÓGICA DE JUEGO
# ──────────────────────────────────────────────────────────────

def load_matches() -> pd.DataFrame:
    required = {"match_id", "group", "home", "away", "match_date", "venue", "kickoff_at"}
    if not MATCHES_FILE.exists():
        st.error("No existe matches_2026.csv. Revisa el repositorio.")
        return pd.DataFrame(columns=sorted(required))
    df = pd.read_csv(MATCHES_FILE).fillna("")
    missing = required - set(df.columns)
    if missing:
        st.error(f"matches_2026.csv no tiene estas columnas: {', '.join(sorted(missing))}")
        return pd.DataFrame(columns=sorted(required))
    df["match_id"] = df["match_id"].astype(str)
    df["group"] = df["group"].astype(str)
    return df


MATCHES = load_matches()
GROUPS = sorted(MATCHES["group"].dropna().unique().tolist()) if not MATCHES.empty else []
MATCH_INDEX = {row.match_id: row for row in MATCHES.itertuples(index=False)}


def parse_kickoff(value: str | None) -> datetime | None:
    if not value or str(value).strip() == "":
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=APP_TZ)
        return dt.astimezone(APP_TZ)
    except Exception:
        return None


def match_label(row: Any) -> str:
    return f"{row.match_id} · Grupo {row.group}: {row.home} vs {row.away}"


def format_match_datetime(row: Any) -> str:
    kickoff = parse_kickoff(getattr(row, "kickoff_at", ""))
    if kickoff:
        return kickoff.strftime(f"%d %b %Y · %H:%M ({APP_TZ_NAME})")
    raw_date = getattr(row, "match_date", "")
    return f"{raw_date} · horario por cargar"


def is_locked(row: Any, locks: dict[str, bool], results: dict[str, dict[str, int]]) -> bool:
    if row.match_id in results:
        return True
    if locks.get(row.match_id, False):
        return True
    kickoff = parse_kickoff(getattr(row, "kickoff_at", ""))
    return bool(kickoff and datetime.now(APP_TZ) >= kickoff)


def calculate_points(pred_h: int, pred_a: int, real_h: int, real_a: int) -> int:
    if pred_h == real_h and pred_a == real_a:
        return 3
    pred_sign = (pred_h > pred_a) - (pred_h < pred_a)
    real_sign = (real_h > real_a) - (real_h < real_a)
    return 1 if pred_sign == real_sign else 0


def point_label(points: int) -> str:
    return {3: "🎯 Exacto · +3", 1: "✅ Resultado · +1", 0: "❌ Sin puntos"}.get(points, "")


def build_standings(users: list[dict[str, Any]], all_predictions: dict[str, Any], results: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for user in users:
        username = user["username"]
        display = user.get("display_name") or username
        preds = all_predictions.get(username, {})
        points = exacts = correct = evaluated = pronosticados = diff_total = 0
        for match_id, pred in preds.items():
            pronosticados += 1
            result = results.get(match_id)
            if not result:
                continue
            evaluated += 1
            p_h = int(pred["home_goals"])
            p_a = int(pred["away_goals"])
            r_h = int(result["home_goals"])
            r_a = int(result["away_goals"])
            pts = calculate_points(p_h, p_a, r_h, r_a)
            points += pts
            exacts += int(pts == 3)
            correct += int(pts >= 1)
            diff_total += abs(p_h - r_h) + abs(p_a - r_a)
        avg = round(points / evaluated, 2) if evaluated else 0.0
        rows.append(
            {
                "Usuario": display,
                "Puntos": points,
                "Exactos 🎯": exacts,
                "Acertados ✅": correct,
                "Dif. marcador": diff_total,
                "Evaluados": evaluated,
                "Pronosticados": pronosticados,
                "Promedio": avg,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(
        ["Puntos", "Exactos 🎯", "Acertados ✅", "Dif. marcador", "Pronosticados"],
        ascending=[False, False, False, True, False],
    ).reset_index(drop=True)


def register_user(username: str, password: str) -> tuple[bool, str]:
    username = normalize_username(username)
    if not username or not password:
        return False, "Completa usuario y contraseña."
    if not USERNAME_RE.fullmatch(username):
        return False, "Usa de 3 a 40 caracteres: letras, números, punto, guion bajo, espacio o guion."
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres."
    if STORE.get_user(username):
        return False, "Ese usuario ya existe."
    STORE.create_user(username, make_password_hash(password))
    return True, "Cuenta creada. Ahora inicia sesión."


def login_user(username: str, password: str) -> tuple[bool, str]:
    username = normalize_username(username)
    record = STORE.get_user(username)
    if not record:
        return False, "Credenciales incorrectas."
    if verify_password(password, record.get("password_hash", "")):
        # Migra hashes SHA256 legados a PBKDF2 en el primer login exitoso.
        if not record.get("password_hash", "").startswith("pbkdf2_sha256$"):
            STORE.update_user_hash(username, make_password_hash(password))
        st.session_state.logged_in = True
        st.session_state.current_user = record["username"]
        return True, "Sesión iniciada."
    return False, "Credenciales incorrectas."

# ──────────────────────────────────────────────────────────────
# ESTADO DE SESIÓN
# ──────────────────────────────────────────────────────────────
for key, default in {
    "logged_in": False,
    "current_user": "",
    "is_admin": False,
}.items():
    st.session_state.setdefault(key, default)

# Datos vivos
USERS = STORE.list_users()
ALL_PREDS = STORE.list_all_predictions()
RESULTS = STORE.list_results()
LOCKS = STORE.list_locks()
STANDINGS = build_standings(USERS, ALL_PREDS, RESULTS)

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────
st.markdown(
    """
<div class="header-banner">
  <h1>⚽ Quinela Mundial 2026</h1>
  <p>Plataforma de pronósticos · Posgrado Instituto Mexicano del Petróleo</p>
</div>
""",
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔑 Acceso")
    if not st.session_state.logged_in:
        login_tab, reg_tab = st.tabs(["Entrar", "Registrarse"])
        with login_tab:
            login_name = st.text_input("Usuario", key="login_name")
            login_pw = st.text_input("Contraseña", type="password", key="login_pw")
            if st.button("Iniciar sesión", use_container_width=True):
                ok, msg = login_user(login_name, login_pw)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
        with reg_tab:
            reg_name = st.text_input("Elige un usuario", placeholder="Nombre Apellido", key="reg_name")
            reg_pw = st.text_input("Contraseña", type="password", key="reg_pw")
            if st.button("Crear cuenta", use_container_width=True):
                ok, msg = register_user(reg_name, reg_pw)
                (st.success if ok else st.error)(msg)
    else:
        st.success(f"✅ {st.session_state.current_user}")
        my_preds = STORE.get_predictions(st.session_state.current_user)
        my_key = user_key(st.session_state.current_user)
        my_row = STANDINGS[STANDINGS["Usuario"].str.casefold() == my_key] if not STANDINGS.empty else pd.DataFrame()
        my_points = int(my_row.iloc[0]["Puntos"]) if not my_row.empty else 0
        played = int(my_row.iloc[0]["Evaluados"]) if not my_row.empty else 0
        st.markdown(
            f"""
            <div class="metric-card"><div class="label">Mis puntos</div><div class="value">{my_points}</div></div>
            <div class="metric-card"><div class="label">Pronosticados / evaluados</div><div class="value">{len(my_preds)} / {played}</div></div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.current_user = ""
            st.session_state.is_admin = False
            st.rerun()

    st.divider()
    st.caption(
        "🎯 Marcador exacto = **3 pts**\n\n"
        "✅ Resultado correcto = **1 pt**\n\n"
        "❌ Fallo = **0 pts**"
    )
    st.caption(f"Base de datos: **{STORE.name}** · Zona horaria: **{APP_TZ_NAME}**")
    if isinstance(STORE, LocalStore):
        st.warning("Modo local: útil para pruebas. Para producción en Streamlit Cloud usa Supabase.")

# ──────────────────────────────────────────────────────────────
# PESTAÑAS
# ──────────────────────────────────────────────────────────────
tab_table, tab_preds, tab_results, tab_admin = st.tabs(
    ["🏆 Tabla General", "📝 Mis Pronósticos", "📊 Resultados", "⚙️ Administración"]
)

# ════════════════════════════════════════
# TABLA GENERAL
# ════════════════════════════════════════
with tab_table:
    st.subheader("Clasificación global")
    if STANDINGS.empty:
        st.info("La tabla se activará cuando haya participantes registrados.")
    else:
        df_show = STANDINGS.copy()
        df_show.insert(0, "Pos.", range(1, len(df_show) + 1))
        st.dataframe(
            df_show,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Puntos": st.column_config.NumberColumn(format="%d pts"),
                "Promedio": st.column_config.NumberColumn(format="%.2f"),
            },
        )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Partidos con resultado", f"{len(RESULTS)} / {len(MATCHES)}")
    c2.metric("Participantes", len(USERS))
    c3.metric("Pronósticos totales", sum(len(v) for v in ALL_PREDS.values()))
    c4.metric("Partidos bloqueados", sum(1 for r in MATCHES.itertuples(index=False) if is_locked(r, LOCKS, RESULTS)))

# ════════════════════════════════════════
# MIS PRONÓSTICOS
# ════════════════════════════════════════
with tab_preds:
    st.subheader("Mis pronósticos")
    if not st.session_state.logged_in:
        st.warning("Inicia sesión para registrar o actualizar tus pronósticos.")
    elif MATCHES.empty:
        st.error("No se cargó el calendario de partidos.")
    else:
        current_user = st.session_state.current_user
        my_preds = STORE.get_predictions(current_user)

        f1, f2, f3 = st.columns([1, 2, 2])
        group_filter = f1.selectbox("Grupo", ["Todos"] + GROUPS, key="pred_group")
        text_filter = f2.text_input("Buscar equipo", placeholder="México, Brasil, Argentina…", key="pred_search")
        status_filter = f3.selectbox("Estado", ["Todos", "Abiertos", "Bloqueados", "Con resultado"], key="pred_status")

        filtered = []
        for row in MATCHES.itertuples(index=False):
            locked = is_locked(row, LOCKS, RESULTS)
            has_result = row.match_id in RESULTS
            if group_filter != "Todos" and row.group != group_filter:
                continue
            if text_filter and text_filter.casefold() not in f"{row.home} {row.away}".casefold():
                continue
            if status_filter == "Abiertos" and locked:
                continue
            if status_filter == "Bloqueados" and not locked:
                continue
            if status_filter == "Con resultado" and not has_result:
                continue
            filtered.append(row)

        if not filtered:
            st.info("No hay partidos que coincidan con los filtros.")
        else:
            for start in range(0, len(filtered), 2):
                cols = st.columns(2)
                for offset, col in enumerate(cols):
                    if start + offset >= len(filtered):
                        continue
                    row = filtered[start + offset]
                    pred = my_preds.get(row.match_id)
                    result = RESULTS.get(row.match_id)
                    locked = is_locked(row, LOCKS, RESULTS)
                    with col:
                        with st.container(border=True):
                            status_badge = "result-badge" if result else ("locked-badge" if locked else "open-badge")
                            status_text = "Resultado" if result else ("Bloqueado" if locked else "Abierto")
                            st.markdown(
                                f'<span class="group-badge">Grupo {row.group}</span> '
                                f'<span class="{status_badge}">{status_text}</span>',
                                unsafe_allow_html=True,
                            )
                            st.markdown(f"**{row.home}** vs **{row.away}**")
                            st.caption(f"📅 {format_match_datetime(row)} · 📍 {row.venue}")

                            if result:
                                st.success(f"Resultado oficial: **{result['home_goals']} – {result['away_goals']}**")
                            if pred:
                                line = f"Tu pronóstico: **{pred['home_goals']} – {pred['away_goals']}**"
                                if result:
                                    pts = calculate_points(
                                        int(pred["home_goals"]), int(pred["away_goals"]),
                                        int(result["home_goals"]), int(result["away_goals"]),
                                    )
                                    line += f" · {point_label(pts)}"
                                st.info(line)

                            if locked:
                                if not pred:
                                    st.caption("Sin pronóstico registrado antes del bloqueo.")
                                continue

                            with st.form(key=f"pred_form_{row.match_id}"):
                                a, b = st.columns(2)
                                default_h = int(pred["home_goals"]) if pred else 0
                                default_a = int(pred["away_goals"]) if pred else 0
                                home_goals = a.number_input(row.home, min_value=0, max_value=30, step=1, value=default_h)
                                away_goals = b.number_input(row.away, min_value=0, max_value=30, step=1, value=default_a)
                                if st.form_submit_button("💾 Guardar pronóstico", use_container_width=True):
                                    # Revalidar bloqueo al momento exacto del submit.
                                    fresh_results = STORE.list_results()
                                    fresh_locks = STORE.list_locks()
                                    if is_locked(row, fresh_locks, fresh_results):
                                        st.error("Este partido ya está bloqueado. No se guardó el cambio.")
                                    else:
                                        STORE.upsert_prediction(current_user, row.match_id, int(home_goals), int(away_goals))
                                        st.success("Pronóstico guardado.")
                                        st.rerun()

# ════════════════════════════════════════
# RESULTADOS
# ════════════════════════════════════════
with tab_results:
    st.subheader("Resultados oficiales")
    group_results = st.selectbox("Filtrar por grupo", ["Todos"] + GROUPS, key="res_group")
    rows = []
    for row in MATCHES.itertuples(index=False):
        if group_results != "Todos" and row.group != group_results:
            continue
        result = RESULTS.get(row.match_id)
        if result:
            rows.append(
                {
                    "Grupo": row.group,
                    "Partido": f"{row.home} vs {row.away}",
                    "Resultado": f"{result['home_goals']} – {result['away_goals']}",
                    "Fecha": row.match_date,
                    "Sede": row.venue,
                }
            )
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay resultados cargados para este filtro.")

# ════════════════════════════════════════
# ADMIN
# ════════════════════════════════════════
with tab_admin:
    st.subheader("Panel de administración")

    if not ADMIN_PASSWORD and not ADMIN_PASSWORD_HASH:
        st.warning("Configura ADMIN_PASSWORD o ADMIN_PASSWORD_HASH en los secretos de Streamlit.")

    if not st.session_state.is_admin:
        admin_pw = st.text_input("Contraseña de administrador", type="password", key="admin_pw")
        if st.button("Entrar como admin", use_container_width=True):
            if verify_admin_password(admin_pw):
                st.session_state.is_admin = True
                st.success("Acceso concedido.")
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")

    if st.session_state.is_admin:
        st.success("✅ Modo administrador activo")
        admin_result_tab, admin_lock_tab, admin_export_tab = st.tabs(["Resultados", "Bloqueos", "Respaldos"])

        with admin_result_tab:
            st.markdown("#### Publicar o corregir resultado")
            if MATCHES.empty:
                st.error("No hay calendario cargado.")
            else:
                group_admin = st.selectbox("Grupo", GROUPS, key="admin_group")
                matches_admin = [r for r in MATCHES.itertuples(index=False) if r.group == group_admin]
                selected_idx = st.selectbox(
                    "Partido",
                    range(len(matches_admin)),
                    format_func=lambda i: match_label(matches_admin[i]),
                    key="admin_match_result",
                )
                row = matches_admin[selected_idx]
                existing = RESULTS.get(row.match_id, {})
                a, b = st.columns(2)
                res_h = a.number_input(f"Goles {row.home}", min_value=0, max_value=30, step=1, value=int(existing.get("home_goals", 0)), key="res_h")
                res_a = b.number_input(f"Goles {row.away}", min_value=0, max_value=30, step=1, value=int(existing.get("away_goals", 0)), key="res_a")
                if existing:
                    st.info(f"Resultado actual: {existing['home_goals']} – {existing['away_goals']}. Se sobreescribirá.")
                if st.button("📥 Publicar resultado", use_container_width=True):
                    STORE.upsert_result(row.match_id, int(res_h), int(res_a))
                    STORE.set_lock(row.match_id, True)
                    st.success("Resultado publicado y partido bloqueado.")
                    st.rerun()

                st.divider()
                st.markdown("#### Eliminar resultado")
                result_ids = sorted(RESULTS.keys())
                if result_ids:
                    del_id = st.selectbox(
                        "Resultado a eliminar",
                        result_ids,
                        format_func=lambda mid: match_label(MATCH_INDEX.get(mid)) if mid in MATCH_INDEX else mid,
                        key="delete_result_id",
                    )
                    if st.button("Eliminar resultado seleccionado", type="secondary"):
                        STORE.delete_result(del_id)
                        st.success("Resultado eliminado. El bloqueo manual se conserva por seguridad.")
                        st.rerun()
                else:
                    st.caption("No hay resultados cargados.")

        with admin_lock_tab:
            st.markdown("#### Bloqueo manual de pronósticos")
            st.caption("Útil cuando no tienes kickoff_at exacto en el CSV o quieres cerrar un partido antes.")
            group_lock = st.selectbox("Grupo", GROUPS, key="lock_group")
            lock_matches = [r for r in MATCHES.itertuples(index=False) if r.group == group_lock]
            lock_idx = st.selectbox(
                "Partido",
                range(len(lock_matches)),
                format_func=lambda i: match_label(lock_matches[i]),
                key="lock_match_idx",
            )
            lock_row = lock_matches[lock_idx]
            current_lock = bool(LOCKS.get(lock_row.match_id, False))
            desired_lock = st.toggle("Bloqueado manualmente", value=current_lock, key="desired_lock")
            if st.button("Guardar bloqueo", use_container_width=True):
                STORE.set_lock(lock_row.match_id, desired_lock)
                st.success("Bloqueo actualizado.")
                st.rerun()

        with admin_export_tab:
            st.markdown("#### Respaldo")
            payload = json.dumps(STORE.export_all(), ensure_ascii=False, indent=2, default=str)
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
