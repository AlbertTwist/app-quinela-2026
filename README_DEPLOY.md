# Quinela Mundial 2026 · Posgrado IMP — v4

Versión reforzada para GitHub + Streamlit Cloud + Supabase.

## Archivos principales

```text
app.py                    ← App principal
matches_2026.csv          ← Calendario y kickoff_at
requirements.txt          ← Dependencias de Streamlit Cloud, ya incluye Supabase
supabase_schema.sql       ← Tablas de Supabase, incluida auditoría
tools/hash_password.py    ← Genera ADMIN_PASSWORD_HASH seguro
data/.gitkeep             ← Mantiene carpeta data/ para modo local
.streamlit/config.toml    ← Tema visual
.gitignore                ← Evita subir secrets y datos locales
```

## Secrets recomendados en Streamlit Cloud

En **App → Settings → Secrets**:

```toml
APP_TZ = "America/Mexico_City"
ADMIN_PASSWORD_HASH = "pbkdf2_sha256$260000$..."

SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "TU_SERVICE_ROLE_KEY"

# Opcionales
POINTS_EXACT = 3
POINTS_RESULT = 1
ENABLE_REGISTRATION = true
```

Puedes generar el hash de admin con:

```bash
python tools/hash_password.py "tu_password_seguro"
```

También funciona `ADMIN_PASSWORD = "..."`, pero `ADMIN_PASSWORD_HASH` es preferible.

## Supabase

1. Crea proyecto en Supabase.
2. Abre **SQL Editor**.
3. Ejecuta todo el contenido de `supabase_schema.sql`.
4. Copia `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` a los Secrets de Streamlit.
5. Reinicia/redeploy la app.

`requirements.txt` ya incluye `supabase>=2.6`, por lo que Streamlit Cloud instalará el backend sin tener que renombrar archivos.

## Mejoras v4

- Supabase incluido por defecto para evitar que la app caiga silenciosamente a JSON local en producción.
- Puntos configurables desde Secrets: `POINTS_EXACT` y `POINTS_RESULT`.
- Registro abierto/cerrado desde `ENABLE_REGISTRATION`.
- Nueva pestaña **Reglamento** para participantes.
- Panel admin ampliado: participantes, exportación CSV de pronósticos y auditoría.
- Tabla `quinela_audit_log` para registrar altas de usuario, resultados, eliminaciones y bloqueos manuales.
- Validación básica de calendario: IDs duplicados, kickoff faltante o formato inválido.
- Descargas CSV con `utf-8-sig` para abrir correctamente en Excel.

## Ejecución local

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Sin Supabase configurado, la app usará `data/quinela_data.json`. Ese modo sirve para pruebas, no para producción.

## Sistema de puntos

| Resultado | Puntos por defecto |
|---|---:|
| Marcador exacto | 3 |
| Resultado correcto | 1 |
| Fallo | 0 |

Desempate: Puntos → Exactos → Acertados → menor diferencia total de marcador → mayor número de pronósticos.

## Notas operativas

- No subas `.streamlit/secrets.toml`, `.env`, `.env.local` ni `data/quinela_data.json`.
- Para cerrar registros cuando empiece el torneo, pon `ENABLE_REGISTRATION = false` en Secrets.
- Si cambia un horario, edita `matches_2026.csv`, confirma el `kickoff_at` y redeploy.
