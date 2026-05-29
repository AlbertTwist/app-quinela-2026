import streamlit as st
import pandas as pd
import numpy as np
import hashlib
import os

# ==========================================
# 1. CONFIGURACIÓN Y PERSISTENCIA
# ==========================================
st.set_page_config(page_title="Quinela Mundial 2026 - Posgrado IMP", page_icon="🏆", layout="wide")

ARCHIVOS = {
    'usuarios': 'usuarios.csv',
    'pronosticos': 'pronosticos.csv',
    'resultados': 'resultados.csv'
}

# Inicializar archivos si no existen en el entorno
if not os.path.exists(ARCHIVOS['usuarios']):
    pd.DataFrame(columns=['Usuario', 'Password_Hash']).to_csv(ARCHIVOS['usuarios'], index=False)
if not os.path.exists(ARCHIVOS['pronosticos']):
    pd.DataFrame(columns=['Usuario', 'Partido', 'Goles_Local', 'Goles_Visit']).to_csv(ARCHIVOS['pronosticos'], index=False)
if not os.path.exists(ARCHIVOS['resultados']):
    pd.DataFrame(columns=['Partido', 'Goles_Local_Real', 'Goles_Visit_Real']).to_csv(ARCHIVOS['resultados'], index=False)

# ==========================================
# 2. MOTOR DE AUTENTICACIÓN
# ==========================================
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def registrar_usuario(usuario, password):
    df_users = pd.read_csv(ARCHIVOS['usuarios'])
    if usuario in df_users['Usuario'].values:
        return False # El usuario ya existe
    nuevo_user = pd.DataFrame({'Usuario': [usuario], 'Password_Hash': [hash_password(password)]})
    nuevo_user.to_csv(ARCHIVOS['usuarios'], mode='a', header=False, index=False)
    return True

def validar_usuario(usuario, password):
    df_users = pd.read_csv(ARCHIVOS['usuarios'])
    if usuario not in df_users['Usuario'].values:
        return False
    user_hash = df_users.loc[df_users['Usuario'] == usuario, 'Password_Hash'].values[0]
    return user_hash == hash_password(password)

# Variables de sesión para mantener al usuario conectado
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'current_user' not in st.session_state:
    st.session_state.current_user = ""

# ==========================================
# 3. BASE DE DATOS DE PARTIDOS (Fase de Grupos Oficial)
# ==========================================
partidos_fase_grupos = [
    # Grupo A
    "México vs Sudáfrica", "Corea del Sur vs Chequia", "México vs Corea del Sur", 
    "Sudáfrica vs Chequia", "México vs Chequia", "Sudáfrica vs Corea del Sur",
    # Grupo B
    "Canadá vs Bosnia y Herzegovina", "Qatar vs Suiza", "Canadá vs Qatar", 
    "Bosnia y Herzegovina vs Suiza", "Canadá vs Suiza", "Bosnia y Herzegovina vs Qatar",
    # Grupo C
    "Brasil vs Marruecos", "Haití vs Escocia", "Brasil vs Haití", 
    "Marruecos vs Escocia", "Brasil vs Escocia", "Marruecos vs Haití",
    # Grupo D
    "Estados Unidos vs Paraguay", "Australia vs Turquía", "Estados Unidos vs Australia", 
    "Paraguay vs Turquía", "Estados Unidos vs Turquía", "Paraguay vs Australia",
    # Grupo E
    "Alemania vs Curazao", "Costa de Marfil vs Ecuador", "Alemania vs Costa de Marfil", 
    "Curazao vs Ecuador", "Alemania vs Ecuador", "Curazao vs Costa de Marfil",
    # Grupo F
    "Países Bajos vs Japón", "Suecia vs Túnez", "Países Bajos vs Suecia", 
    "Japón vs Túnez", "Países Bajos vs Túnez", "Japón vs Suecia",
    # Grupo G
    "Bélgica vs Egipto", "Irán vs Nueva Zelanda", "Bélgica vs Irán", 
    "Egipto vs Nueva Zelanda", "Bélgica vs Nueva Zelanda", "Egipto vs Irán",
    # Grupo H
    "España vs Cabo Verde", "Arabia Saudita vs Uruguay", "España vs Arabia Saudita", 
    "Cabo Verde vs Uruguay", "España vs Uruguay", "Cabo Verde vs Arabia Saudita",
    # Grupo I
    "Francia vs Senegal", "Irak vs Noruega", "Francia vs Irak", 
    "Senegal vs Noruega", "Francia vs Noruega", "Senegal vs Irak",
    # Grupo J
    "Argentina vs Argelia", "Austria vs Jordania", "Argentina vs Austria", 
    "Argelia vs Jordania", "Argentina vs Jordania", "Argelia vs Austria",
    # Grupo K
    "Portugal vs RD Congo", "Uzbekistán vs Colombia", "Portugal vs Uzbekistán", 
    "RD Congo vs Colombia", "Portugal vs Colombia", "RD Congo vs Uzbekistán",
    # Grupo L
    "Inglaterra vs Croacia", "Ghana vs Panamá", "Inglaterra vs Ghana", 
    "Croacia vs Panamá", "Inglaterra vs Panamá", "Croacia vs Ghana"
]

# ==========================================
# 4. LÓGICA DE PUNTUACIÓN Y GUARDADO
# ==========================================
def calcular_puntos(row):
    if pd.isna(row.get('Goles_Local_Real')): return 0
    pred_L, pred_V = row['Goles_Local'], row['Goles_Visit']
    real_L, real_V = row['Goles_Local_Real'], row['Goles_Visit_Real']
    
    if (pred_L == real_L) and (pred_V == real_V): return 3
    if np.sign(pred_L - pred_V) == np.sign(real_L - real_V): return 1
    return 0

def guardar_pronostico(usuario, partido, g_L, g_V):
    df_pro = pd.read_csv(ARCHIVOS['pronosticos'])
    mask = (df_pro['Usuario'] == usuario) & (df_pro['Partido'] == partido)
    
    if not df_pro[mask].empty:
        # Actualiza el pronóstico si ya existía
        df_pro.loc[mask, ['Goles_Local', 'Goles_Visit']] = [g_L, g_V]
        df_pro.to_csv(ARCHIVOS['pronosticos'], index=False)
    else:
        # Agrega un pronóstico nuevo
        nuevo = pd.DataFrame({'Usuario': [usuario], 'Partido': [partido], 'Goles_Local': [g_L], 'Goles_Visit': [g_V]})
        nuevo.to_csv(ARCHIVOS['pronosticos'], mode='a', header=False, index=False)

# ==========================================
# 5. INTERFAZ GRÁFICA DEL DASHBOARD
# ==========================================
st.title("⚽ Quinela Mundial 2026")
st.markdown("Bienvenidos a la plataforma oficial de pronósticos del Posgrado del Instituto Mexicano del Petróleo.")

# --- BARRA LATERAL: LOGIN Y REGISTRO ---
with st.sidebar:
    if not st.session_state.logged_in:
        st.header("🔑 Control de Acceso")
        tipo_acceso = st.radio("Elige una opción:", ["Iniciar Sesión", "Crear Cuenta"])
        
        user_input = st.text_input("Usuario (Ej. Nombre_Apellido)").strip()
        pass_input = st.text_input("Contraseña", type="password")
        
        if tipo_acceso == "Crear Cuenta":
            if st.button("Registrarse"):
                if user_input and pass_input:
                    if registrar_usuario(user_input, pass_input):
                        st.success("Cuenta creada exitosamente. Ya puedes iniciar sesión.")
                    else:
                        st.error("Ese usuario ya está registrado. Elige otro nombre.")
                else:
                    st.warning("Llena ambos campos.")
        else:
            if st.button("Entrar"):
                if validar_usuario(user_input, pass_input):
                    st.session_state.logged_in = True
                    st.session_state.current_user = user_input
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
    else:
        st.success(f"Sesión activa: **{st.session_state.current_user}**")
        if st.button("Cerrar Sesión"):
            st.session_state.logged_in = False
            st.session_state.current_user = ""
            st.rerun()

# --- PESTAÑAS DE NAVEGACIÓN ---
tab_tabla, tab_registro, tab_admin = st.tabs(["🏆 Tabla de Posiciones", "📝 Mis Pronósticos", "⚙️ Panel de Administración"])

# --- PESTAÑA 1: TABLA GENERAL ---
with tab_tabla:
    df_p = pd.read_csv(ARCHIVOS['pronosticos'])
    df_r = pd.read_csv(ARCHIVOS['resultados'])
    
    if df_p.empty:
        st.info("La tabla se generará cuando se registre el primer pronóstico.")
    else:
        df_full = pd.merge(df_p, df_r, on='Partido', how='left')
        df_full['Puntos'] = df_full.apply(calcular_puntos, axis=1)
        
        tabla = df_full.groupby('Usuario')['Puntos'].sum().reset_index()
        tabla = tabla.sort_values(by='Puntos', ascending=False).reset_index(drop=True)
        tabla.index += 1
        tabla.index.name = 'Posición'
        
        st.subheader("Clasificación Global")
        st.dataframe(tabla.style.highlight_max(subset=['Puntos'], color='rgba(46, 123, 50, 0.5)'), use_container_width=True)

# --- PESTAÑA 2: REGISTRO DE PRONÓSTICOS ---
with tab_registro:
    if st.session_state.logged_in:
        st.subheader("Ingresa o modifica tus resultados")
        with st.form("form_pronosticos"):
            partido_sel = st.selectbox("Selecciona el Partido", partidos_fase_grupos)
            c1, c2 = st.columns(2)
            g_L = c1.number_input("Goles Local", min_value=0, step=1)
            g_V = c2.number_input("Goles Visitante", min_value=0, step=1)
            
            if st.form_submit_button("Guardar Marcador"):
                guardar_pronostico(st.session_state.current_user, partido_sel, g_L, g_V)
                st.success(f"Pronóstico guardado exitosamente para el encuentro: {partido_sel}")
    else:
        st.warning("⚠️ Debes iniciar sesión en el menú de la izquierda para poder registrar tus pronósticos.")

# --- PESTAÑA 3: PANEL DE ADMINISTRADOR ---
with tab_admin:
    st.write("Módulo exclusivo para la carga de marcadores reales.")
    admin_pass = st.text_input("Contraseña de Administrador", type="password")
    
    # Cambia "AdminIMP26" por tu contraseña segura preferida
    if admin_pass == "AdminIMP26": 
        st.success("Acceso de administrador concedido.")
        with st.form("form_admin"):
            partido_r = st.selectbox("Partido Concluido", partidos_fase_grupos)
            c1, c2 = st.columns(2)
            r_L = c1.number_input("Resultado Final Local", min_value=0, step=1)
            r_V = c2.number_input("Resultado Final Visitante", min_value=0, step=1)
            
            if st.form_submit_button("Actualizar Torneo"):
                nuevo_res = pd.DataFrame({'Partido': [partido_r], 'Goles_Local_Real': [r_L], 'Goles_Visit_Real': [r_V]})
                nuevo_res.to_csv(ARCHIVOS['resultados'], mode='a', header=False, index=False)
                st.success("Marcador oficial publicado. La tabla global se ha recalculado.")