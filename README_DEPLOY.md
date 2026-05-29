# Quinela Mundial 2026 · Posgrado IMP

Versión robusta para desplegar en GitHub + Streamlit Community Cloud.

## Qué cambió

- Persistencia con Supabase cuando configuras secretos.
- Respaldo JSON local únicamente para desarrollo.
- Contraseñas de usuarios con PBKDF2 + salt.
- Administración con contraseña en `st.secrets`.
- Bloqueo automático por `kickoff_at` y bloqueo manual desde el panel admin.
- Fixture en `matches_2026.csv`, no dentro del código.
- IDs estables por partido (`M001`, `M002`, etc.).

## Archivos del proyecto

```text
quinela_streamlit_mejorada/
├── app.py
├── matches_2026.csv
├── requirements.txt
├── supabase_schema.sql
├── README_DEPLOY.md
├── .gitignore
├── .streamlit/
│   └── config.toml
└── tools/
    └── hash_password.py
```

## Configuración recomendada con Supabase

1. Entra a Supabase y crea un proyecto.
2. Abre **SQL Editor** y ejecuta `supabase_schema.sql`.
3. En Streamlit Community Cloud abre tu app → **Settings** → **Secrets**.
4. Pega algo como esto:

```toml
APP_TZ = "America/Mexico_City"
ADMIN_PASSWORD = "cambia_esto_por_un_password_fuerte"
SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "TU_SERVICE_ROLE_KEY"
```

Para mayor seguridad puedes usar `ADMIN_PASSWORD_HASH` en vez de `ADMIN_PASSWORD`:

```bash
python tools/hash_password.py "tu_password_seguro"
```

Luego pega el resultado en secrets:

```toml
ADMIN_PASSWORD_HASH = "pbkdf2_sha256$260000$..."
```

No subas `.streamlit/secrets.toml` a GitHub.

## Despliegue en Streamlit

1. Sube estos archivos al repositorio de GitHub.
2. Verifica que `requirements.txt` esté en la raíz.
3. En Streamlit Community Cloud selecciona el repo, rama y `app.py` como entrypoint.
4. Configura los secrets antes de compartir la app.

## Calendario y bloqueos

`matches_2026.csv` contiene fecha y sede de fase de grupos. La columna `kickoff_at` está vacía para evitar bloquear con horarios inventados. Para bloqueo automático, llena `kickoff_at` con formato ISO:

```csv
2026-06-11T13:00:00-06:00
```

Si aún no tienes la hora exacta, usa el panel de administración → **Bloqueos** para cerrar manualmente cada partido.

## Ejecución local

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows PowerShell
pip install -r requirements.txt
streamlit run app.py
```

Para probar sin Supabase, la app usará `data/quinela_data.json`. Ese archivo está ignorado por Git.
