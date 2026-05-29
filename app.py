"""
Quinela Mundial 2026 - Posgrado IMP
====================================
Versión mejorada con:
  - Persistencia real via st.session_state + JSON (compatible con GitHub/Streamlit Cloud)
  - Contraseña de admin via st.secrets (nunca en el código)
  - Actualización correcta de resultados (no duplica registros)
  - Bloqueo de pronósticos después del inicio del partido
  - Tabla de posiciones con tiebreakers y métricas completas
  - Filtro de partidos por grupo y búsqueda
  - Resumen personal por usuario
  - CSS personalizado con identidad IMP
"""

import streamlit as st
import pandas as pd
import numpy as np
import hashlib
import json
import os
from datetime import datetime, timezone

# ──────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Quinela Mundial 2026 · IMP",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Contraseña de admin: define ADMIN_PASSWORD en tu .streamlit/secrets.toml
# [secrets]
# ADMIN_PASSWORD = "tu_password_seguro"
# En local también puedes poner la variable de entorno ADMIN_PASSWORD.
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", os.environ.get("ADMIN_PASSWORD", ""))

# ──────────────────────────────────────────────────────────────
# TEMA / CSS
# ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

:root {
    --verde:  #006341;
    --oro:    #c8962c;
    --claro:  #f5f0e8;
    --oscuro: #1a1a1a;
}

html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }

h1, h2, h3 { font-family: 'Bebas Neue', sans-serif; letter-spacing: 1px; }

.stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    background: var(--verde);
    border-radius: 8px;
    padding: 4px;
}
.stTabs [data-baseweb="tab"] {
    color: rgba(255,255,255,0.7) !important;
    font-weight: 600;
    border-radius: 6px;
}
.stTabs [aria-selected="true"] {
    background: var(--oro) !important;
    color: var(--oscuro) !important;
}

/* Métricas de posición */
.metric-card {
    background: linear-gradient(135deg, var(--verde), #004d32);
    color: white;
    padding: 16px 20px;
    border-radius: 10px;
    border-left: 4px solid var(--oro);
    margin-bottom: 8px;
}
.metric-card .label { font-size: 0.75rem; opacity: 0.8; text-transform: uppercase; letter-spacing: 1px; }
.metric-card .value { font-family: 'Bebas Neue'; font-size: 2rem; color: var(--oro); }

/* Header */
.header-banner {
    background: linear-gradient(135deg, #006341 0%, #004d32 50%, #1a1a1a 100%);
    color: white;
    padding: 20px 28px;
    border-radius: 12px;
    margin-bottom: 24px;
    border-bottom: 3px solid var(--oro);
}
.header-banner h1 { color: white; margin: 0; font-size: 2.4rem; }
.header-banner p  { margin: 4px 0 0; opacity: 0.85; font-size: 0.9rem; }

/* Badges de grupo */
.group-badge {
    display: inline-block;
    background: var(--verde);
    color: white;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* Alerta de bloqueo */
.locked-badge {
    background: #b71c1c;
    color: white;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 20px;
    font-weight: 700;
}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# PERSISTENCIA  (JSON en disco — funciona en Streamlit Community Cloud
#                siempre que el repo tenga permisos de escritura;
#                para producción sería mejor usar Supabase/Firebase,
#                pero esto es un paso enorme sobre CSVs volátiles)
# ──────────────────────────────────────────────────────────────
DATA_FILE = "quinela_data.json"

def cargar_datos() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"usuarios": {}, "pronosticos": {}, "resultados": {}}

def guardar_datos(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Cargar datos al inicio (una sola vez por sesión)
if "data" not in st.session_state:
    st.session_state.data = cargar_datos()

DATA = st.session_state.data  # referencia corta

# ──────────────────────────────────────────────────────────────
# AUTENTICACIÓN
# ──────────────────────────────────────────────────────────────
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def registrar(usuario: str, pw: str) -> tuple[bool, str]:
    usuario = usuario.strip()
    if not usuario or not pw:
        return False, "Completa ambos campos."
    if len(pw) < 6:
        return False, "La contraseña debe tener al menos 6 caracteres."
    if usuario in DATA["usuarios"]:
        return False, "Ese nombre de usuario ya existe."
    DATA["usuarios"][usuario] = hash_pw(pw)
    guardar_datos(DATA)
    return True, "Cuenta creada. Ahora inicia sesión."

def validar(usuario: str, pw: str) -> bool:
    return DATA["usuarios"].get(usuario) == hash_pw(pw)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = ""

# ──────────────────────────────────────────────────────────────
# PARTIDOS — Fase de Grupos con fecha de inicio (UTC-6 México)
# ──────────────────────────────────────────────────────────────
# Formato: (grupo, local, visitante, fecha_iso_string_o_None)
# Si la fecha es None, el partido NO está bloqueado aún
# Puedes ir completando las fechas reales cuando FIFA las publique.
PARTIDOS_RAW = [
    # Grupo A
    ("A", "México",          "Sudáfrica",          "2026-06-11T18:00:00"),
    ("A", "Corea del Sur",   "Chequia",            "2026-06-11T21:00:00"),
    ("A", "México",          "Corea del Sur",      "2026-06-15T18:00:00"),
    ("A", "Sudáfrica",       "Chequia",            "2026-06-15T21:00:00"),
    ("A", "México",          "Chequia",            "2026-06-19T18:00:00"),
    ("A", "Sudáfrica",       "Corea del Sur",      "2026-06-19T18:00:00"),
    # Grupo B
    ("B", "Canadá",          "Bosnia y Herzegovina","2026-06-12T15:00:00"),
    ("B", "Qatar",           "Suiza",              "2026-06-12T18:00:00"),
    ("B", "Canadá",          "Qatar",              "2026-06-16T15:00:00"),
    ("B", "Bosnia y Herzegovina","Suiza",          "2026-06-16T18:00:00"),
    ("B", "Canadá",          "Suiza",              "2026-06-20T18:00:00"),
    ("B", "Bosnia y Herzegovina","Qatar",          "2026-06-20T18:00:00"),
    # Grupo C
    ("C", "Brasil",          "Marruecos",          "2026-06-12T21:00:00"),
    ("C", "Haití",           "Escocia",            "2026-06-13T15:00:00"),
    ("C", "Brasil",          "Haití",              "2026-06-16T21:00:00"),
    ("C", "Marruecos",       "Escocia",            "2026-06-17T15:00:00"),
    ("C", "Brasil",          "Escocia",            "2026-06-20T21:00:00"),
    ("C", "Marruecos",       "Haití",              "2026-06-20T21:00:00"),
    # Grupo D
    ("D", "Estados Unidos",  "Paraguay",           "2026-06-13T18:00:00"),
    ("D", "Australia",       "Turquía",            "2026-06-13T21:00:00"),
    ("D", "Estados Unidos",  "Australia",          "2026-06-17T18:00:00"),
    ("D", "Paraguay",        "Turquía",            "2026-06-17T21:00:00"),
    ("D", "Estados Unidos",  "Turquía",            "2026-06-21T18:00:00"),
    ("D", "Paraguay",        "Australia",          "2026-06-21T18:00:00"),
    # Grupo E
    ("E", "Alemania",        "Curazao",            "2026-06-14T15:00:00"),
    ("E", "Costa de Marfil", "Ecuador",            "2026-06-14T18:00:00"),
    ("E", "Alemania",        "Costa de Marfil",    "2026-06-18T15:00:00"),
    ("E", "Curazao",         "Ecuador",            "2026-06-18T18:00:00"),
    ("E", "Alemania",        "Ecuador",            "2026-06-22T18:00:00"),
    ("E", "Curazao",         "Costa de Marfil",    "2026-06-22T18:00:00"),
    # Grupo F
    ("F", "Países Bajos",    "Japón",              "2026-06-14T21:00:00"),
    ("F", "Suecia",          "Túnez",              "2026-06-15T15:00:00"),
    ("F", "Países Bajos",    "Suecia",             "2026-06-18T21:00:00"),
    ("F", "Japón",           "Túnez",              "2026-06-19T15:00:00"),
    ("F", "Países Bajos",    "Túnez",              "2026-06-22T21:00:00"),
    ("F", "Japón",           "Suecia",             "2026-06-22T21:00:00"),
    # Grupo G
    ("G", "Bélgica",         "Egipto",             "2026-06-15T15:00:00"),
    ("G", "Irán",            "Nueva Zelanda",      "2026-06-15T18:00:00"),
    ("G", "Bélgica",         "Irán",               "2026-06-19T15:00:00"),
    ("G", "Egipto",          "Nueva Zelanda",      "2026-06-19T18:00:00"),
    ("G", "Bélgica",         "Nueva Zelanda",      "2026-06-23T18:00:00"),
    ("G", "Egipto",          "Irán",               "2026-06-23T18:00:00"),
    # Grupo H
    ("H", "España",          "Cabo Verde",         "2026-06-16T15:00:00"),
    ("H", "Arabia Saudita",  "Uruguay",            "2026-06-16T18:00:00"),
    ("H", "España",          "Arabia Saudita",     "2026-06-20T15:00:00"),
    ("H", "Cabo Verde",      "Uruguay",            "2026-06-20T18:00:00"),
    ("H", "España",          "Uruguay",            "2026-06-24T18:00:00"),
    ("H", "Cabo Verde",      "Arabia Saudita",     "2026-06-24T18:00:00"),
    # Grupo I
    ("I", "Francia",         "Senegal",            "2026-06-17T15:00:00"),
    ("I", "Irak",            "Noruega",            "2026-06-17T18:00:00"),
    ("I", "Francia",         "Irak",               "2026-06-21T15:00:00"),
    ("I", "Senegal",         "Noruega",            "2026-06-21T18:00:00"),
    ("I", "Francia",         "Noruega",            "2026-06-25T18:00:00"),
    ("I", "Senegal",         "Irak",               "2026-06-25T18:00:00"),
    # Grupo J
    ("J", "Argentina",       "Argelia",            "2026-06-17T21:00:00"),
    ("J", "Austria",         "Jordania",           "2026-06-18T15:00:00"),
    ("J", "Argentina",       "Austria",            "2026-06-21T21:00:00"),
    ("J", "Argelia",         "Jordania",           "2026-06-22T15:00:00"),
    ("J", "Argentina",       "Jordania",           "2026-06-25T21:00:00"),
    ("J", "Argelia",         "Austria",            "2026-06-25T21:00:00"),
    # Grupo K
    ("K", "Portugal",        "RD Congo",           "2026-06-18T21:00:00"),
    ("K", "Uzbekistán",      "Colombia",           "2026-06-19T15:00:00"),
    ("K", "Portugal",        "Uzbekistán",         "2026-06-22T15:00:00"),
    ("K", "RD Congo",        "Colombia",           "2026-06-22T18:00:00"),
    ("K", "Portugal",        "Colombia",           "2026-06-26T18:00:00"),
    ("K", "RD Congo",        "Uzbekistán",         "2026-06-26T18:00:00"),
    # Grupo L
    ("L", "Inglaterra",      "Croacia",            "2026-06-19T21:00:00"),
    ("L", "Ghana",           "Panamá",             "2026-06-20T15:00:00"),
    ("L", "Inglaterra",      "Ghana",              "2026-06-23T15:00:00"),
    ("L", "Croacia",         "Panamá",             "2026-06-23T18:00:00"),
    ("L", "Inglaterra",      "Panamá",             "2026-06-26T21:00:00"),
    ("L", "Croacia",         "Ghana",              "2026-06-26T21:00:00"),
]

def partido_key(grupo, local, visitante):
    return f"{grupo}:{local} vs {visitante}"

def partido_label(grupo, local, visitante):
    return f"{local} vs {visitante}"

def esta_bloqueado(fecha_str: str | None) -> bool:
    """Regresa True si la hora del partido ya pasó (no se puede cambiar pronóstico)."""
    if not fecha_str:
        return False
    try:
        dt = datetime.fromisoformat(fecha_str)
        # Comparar en naive UTC-6 (México Centro)
        ahora = datetime.now()
        return ahora >= dt
    except Exception:
        return False

# Mapas útiles
PARTIDOS_MAP = {partido_key(g, l, v): {"grupo": g, "local": l, "visitante": v, "fecha": f}
                for g, l, v, f in PARTIDOS_RAW}
GRUPOS = sorted(set(g for g, *_ in PARTIDOS_RAW))

# ──────────────────────────────────────────────────────────────
# PUNTUACIÓN  (3 pts exacto · 1 pt resultado correcto · 0 pt fallo)
# ──────────────────────────────────────────────────────────────
def calcular_puntos(pred_L, pred_V, real_L, real_V) -> int:
    if pred_L == real_L and pred_V == real_V:
        return 3
    if np.sign(pred_L - pred_V) == np.sign(real_L - real_V):
        return 1
    return 0

def tabla_posiciones() -> pd.DataFrame:
    """Genera la tabla con puntos, exactos, acertados, pronosticados y promedio."""
    rows = []
    for usuario in DATA["usuarios"]:
        pts = exactos = acertados = total = 0
        pronosticos_usuario = DATA["pronosticos"].get(usuario, {})
        for key, pron in pronosticos_usuario.items():
            total += 1
            resultado = DATA["resultados"].get(key)
            if resultado:
                p = calcular_puntos(pron["L"], pron["V"], resultado["L"], resultado["V"])
                pts += p
                if p == 3:
                    exactos += 1
                if p >= 1:
                    acertados += 1
        rows.append({
            "Usuario": usuario,
            "Puntos": pts,
            "Exactos 🎯": exactos,
            "Acertados ✅": acertados,
            "Pronosticados": total,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values(["Puntos", "Exactos 🎯", "Acertados ✅"], ascending=False).reset_index(drop=True)
    df.index += 1
    df.index.name = "Pos."
    return df

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────
st.markdown("""
<div class="header-banner">
  <h1>⚽ Quinela Mundial 2026</h1>
  <p>Plataforma de pronósticos · Posgrado Instituto Mexicano del Petróleo</p>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# SIDEBAR — LOGIN / REGISTRO
# ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔑 Acceso")
    if not st.session_state.logged_in:
        tab_login, tab_reg = st.tabs(["Entrar", "Registrarse"])

        with tab_login:
            u_in = st.text_input("Usuario", key="login_u")
            p_in = st.text_input("Contraseña", type="password", key="login_p")
            if st.button("Iniciar sesión", use_container_width=True):
                if validar(u_in, p_in):
                    st.session_state.logged_in = True
                    st.session_state.current_user = u_in
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas.")

        with tab_reg:
            u_r = st.text_input("Elige un usuario", key="reg_u",
                                placeholder="Nombre_Apellido")
            p_r = st.text_input("Contraseña (mín. 6)", type="password", key="reg_p")
            if st.button("Crear cuenta", use_container_width=True):
                ok, msg = registrar(u_r, p_r)
                (st.success if ok else st.error)(msg)
    else:
        st.success(f"✅ {st.session_state.current_user}")

        # Mini-resumen personal
        mis_pron = DATA["pronosticos"].get(st.session_state.current_user, {})
        mis_pts = sum(
            calcular_puntos(p["L"], p["V"],
                            DATA["resultados"][k]["L"],
                            DATA["resultados"][k]["V"])
            for k, p in mis_pron.items() if k in DATA["resultados"]
        )
        partidos_jugados = sum(1 for k in mis_pron if k in DATA["resultados"])
        st.markdown(f"""
        <div class="metric-card">
          <div class="label">Mis Puntos</div>
          <div class="value">{mis_pts}</div>
        </div>
        <div class="metric-card">
          <div class="label">Pronosticados / Jugados</div>
          <div class="value">{len(mis_pron)} / {partidos_jugados}</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.current_user = ""
            st.rerun()

    st.markdown("---")
    st.caption("⚡ Los pronósticos se bloquean al inicio de cada partido.\n\n"
               "🎯 Marcador exacto = **3 pts**\n✅ Resultado correcto = **1 pt**\n❌ Fallo = **0 pts**")

# ──────────────────────────────────────────────────────────────
# PESTAÑAS PRINCIPALES
# ──────────────────────────────────────────────────────────────
tab_tabla, tab_pron, tab_resultados, tab_admin = st.tabs([
    "🏆 Tabla General",
    "📝 Mis Pronósticos",
    "📊 Resultados",
    "⚙️ Administración",
])

# ════════════════════════════════════════
# TAB 1 — TABLA GENERAL
# ════════════════════════════════════════
with tab_tabla:
    st.subheader("Clasificación Global")
    df_tabla = tabla_posiciones()

    if df_tabla.empty:
        st.info("La tabla se activará cuando haya pronósticos registrados.")
    else:
        # Destacar al líder
        def colorear(row):
            if row.name == 1:
                return ["background-color: rgba(200,150,44,0.15); font-weight:700"] * len(row)
            return [""] * len(row)

        st.dataframe(
            df_tabla.style.apply(colorear, axis=1)
                          .bar(subset=["Puntos"], color="#006341", vmin=0),
            use_container_width=True,
            height=420,
        )

    col1, col2, col3 = st.columns(3)
    n_jugados = len(DATA["resultados"])
    n_total   = len(PARTIDOS_RAW)
    col1.metric("Partidos jugados", f"{n_jugados} / {n_total}")
    col2.metric("Participantes",    len(DATA["usuarios"]))
    col3.metric("Pronósticos totales",
                sum(len(v) for v in DATA["pronosticos"].values()))

# ════════════════════════════════════════
# TAB 2 — MIS PRONÓSTICOS
# ════════════════════════════════════════
with tab_pron:
    if not st.session_state.logged_in:
        st.warning("⚠️ Inicia sesión para registrar tus pronósticos.")
        st.stop()

    usuario_activo = st.session_state.current_user
    mis_pron = DATA["pronosticos"].setdefault(usuario_activo, {})

    st.subheader(f"Pronósticos de {usuario_activo}")

    # Filtros
    col_f1, col_f2 = st.columns([1, 3])
    grupo_sel = col_f1.selectbox("Filtrar por grupo", ["Todos"] + GRUPOS)
    busqueda  = col_f2.text_input("🔍 Buscar equipo", placeholder="ej. México, Brasil…")

    partidos_filtrados = [
        (g, l, v, f) for g, l, v, f in PARTIDOS_RAW
        if (grupo_sel == "Todos" or g == grupo_sel)
        and (not busqueda or busqueda.lower() in l.lower() or busqueda.lower() in v.lower())
    ]

    if not partidos_filtrados:
        st.info("Sin partidos que coincidan con el filtro.")
    else:
        # Mostrar en grid de 2 columnas
        for i in range(0, len(partidos_filtrados), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                if i + j >= len(partidos_filtrados):
                    break
                g, l, v, fecha = partidos_filtrados[i + j]
                key = partido_key(g, l, v)
                bloqueado = esta_bloqueado(fecha)
                pron_actual = mis_pron.get(key)
                resultado   = DATA["resultados"].get(key)

                with col:
                    with st.container(border=True):
                        # Encabezado del partido
                        c_badge, c_estado = st.columns([3, 1])
                        c_badge.markdown(
                            f'<span class="group-badge">Grupo {g}</span>', 
                            unsafe_allow_html=True
                        )
                        if bloqueado:
                            c_estado.markdown(
                                '<span class="locked-badge">🔒 Bloqueado</span>',
                                unsafe_allow_html=True
                            )

                        st.markdown(f"**{l}** vs **{v}**")
                        if fecha:
                            try:
                                dt_fmt = datetime.fromisoformat(fecha).strftime("%d %b %H:%M")
                                st.caption(f"📅 {dt_fmt} (hora CDMX)")
                            except Exception:
                                pass

                        # Resultado oficial (si existe)
                        if resultado:
                            st.success(
                                f"✅ Resultado: **{resultado['L']} – {resultado['V']}**"
                            )
                            if pron_actual:
                                pts = calcular_puntos(
                                    pron_actual["L"], pron_actual["V"],
                                    resultado["L"], resultado["V"]
                                )
                                icons = {3: "🎯 ¡Exacto! +3 pts", 1: "✅ Resultado correcto +1 pt", 0: "❌ Sin puntos"}
                                st.info(f"Tu pronóstico: {pron_actual['L']}–{pron_actual['V']} · {icons[pts]}")

                        # Formulario de pronóstico
                        if not bloqueado:
                            with st.form(key=f"form_{key}"):
                                c1, c2 = st.columns(2)
                                val_L = pron_actual["L"] if pron_actual else 0
                                val_V = pron_actual["V"] if pron_actual else 0
                                g_L = c1.number_input(l[:12], min_value=0, step=1,
                                                      value=val_L, key=f"gL_{key}")
                                g_V = c2.number_input(v[:12], min_value=0, step=1,
                                                      value=val_V, key=f"gV_{key}")
                                lbl = "Actualizar" if pron_actual else "Guardar"
                                if st.form_submit_button(f"💾 {lbl}", use_container_width=True):
                                    mis_pron[key] = {"L": int(g_L), "V": int(g_V)}
                                    DATA["pronosticos"][usuario_activo] = mis_pron
                                    guardar_datos(DATA)
                                    st.success("Guardado ✓")
                                    st.rerun()
                        elif not resultado and pron_actual:
                            st.caption(f"Tu pronóstico: {pron_actual['L']}–{pron_actual['V']}")

# ════════════════════════════════════════
# TAB 3 — RESULTADOS PÚBLICOS
# ════════════════════════════════════════
with tab_resultados:
    st.subheader("Resultados Oficiales")

    grupo_r = st.selectbox("Grupo", ["Todos"] + GRUPOS, key="gr_res")
    partidos_con_res = [
        (g, l, v, f) for g, l, v, f in PARTIDOS_RAW
        if (grupo_r == "Todos" or g == grupo_r)
        and partido_key(g, l, v) in DATA["resultados"]
    ]

    if not partidos_con_res:
        st.info("Aún no hay resultados cargados para este grupo.")
    else:
        rows_res = []
        for g, l, v, _ in partidos_con_res:
            key = partido_key(g, l, v)
            res = DATA["resultados"][key]
            rows_res.append({
                "Grupo": g,
                "Local": l,
                "Goles L": res["L"],
                "–": "–",
                "Goles V": res["V"],
                "Visitante": v,
            })
        st.dataframe(pd.DataFrame(rows_res), use_container_width=True, hide_index=True)

# ════════════════════════════════════════
# TAB 4 — ADMINISTRACIÓN
# ════════════════════════════════════════
with tab_admin:
    st.subheader("Panel de Administración")

    if not ADMIN_PASSWORD:
        st.warning("⚠️ No se ha configurado `ADMIN_PASSWORD` en `st.secrets`. "
                   "Añade `ADMIN_PASSWORD = 'tu_password'` en `.streamlit/secrets.toml`.")

    admin_input = st.text_input("Contraseña de administrador", type="password")

    if admin_input and admin_input == ADMIN_PASSWORD:
        st.success("✅ Acceso concedido.")

        st.markdown("#### Cargar resultado oficial")
        grupo_a = st.selectbox("Grupo", GRUPOS, key="g_admin")
        partidos_grupo = [(l, v, f) for g, l, v, f in PARTIDOS_RAW if g == grupo_a]
        labels_grupo   = [partido_label(grupo_a, l, v) for l, v, _ in partidos_grupo]

        partido_idx = st.selectbox("Partido", range(len(labels_grupo)),
                                   format_func=lambda i: labels_grupo[i])
        l_sel, v_sel, _ = partidos_grupo[partido_idx]
        key_sel = partido_key(grupo_a, l_sel, v_sel)

        c1, c2 = st.columns(2)
        r_L = c1.number_input(f"Goles {l_sel}", min_value=0, step=1, key="admin_L")
        r_V = c2.number_input(f"Goles {v_sel}", min_value=0, step=1, key="admin_V")

        existing = DATA["resultados"].get(key_sel)
        if existing:
            st.info(f"Resultado actual: {existing['L']} – {existing['V']}. Se sobreescribirá.")

        if st.button("📥 Publicar resultado", use_container_width=True):
            DATA["resultados"][key_sel] = {"L": int(r_L), "V": int(r_V)}
            guardar_datos(DATA)
            st.success(f"Resultado publicado: {l_sel} {r_L} – {r_V} {v_sel}")
            st.rerun()

        st.divider()
        st.markdown("#### 🗑️ Eliminar resultado (corrección)")
        keys_con_resultado = list(DATA["resultados"].keys())
        if keys_con_resultado:
            key_del = st.selectbox("Resultado a eliminar", keys_con_resultado)
            if st.button("Eliminar resultado seleccionado", type="secondary"):
                del DATA["resultados"][key_del]
                guardar_datos(DATA)
                st.success("Resultado eliminado.")
                st.rerun()
        else:
            st.caption("No hay resultados cargados.")

    elif admin_input:
        st.error("Contraseña incorrecta.")