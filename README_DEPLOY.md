# Quinela Mundial 2026 · Posgrado IMP — v3

## Estructura del proyecto

```
app.py                    ← App principal
matches_2026.csv          ← Calendario completo con kickoff_at en español
requirements.txt          ← Dependencias base (sin supabase)
requirements-supabase.txt ← Dependencia opcional para Supabase
supabase_schema.sql       ← Esquema SQL para Supabase
tools/hash_password.py    ← Genera ADMIN_PASSWORD_HASH seguro
data/.gitkeep             ← Mantiene carpeta data/ en el repo (JSON ignorado)
.gitignore                ← No sube secrets.toml ni quinela_data.json
.streamlit/config.toml    ← Tema visual
```

## Despliegue en Streamlit Community Cloud

### 1. Sube los archivos a GitHub
Asegúrate de que `data/` está en el repo (con `.gitkeep`).
`data/quinela_data.json` está en `.gitignore` y **no** se sube.

### 2. Configura los Secrets
En Streamlit Cloud → tu app → **Settings → Secrets**:

```toml
APP_TZ         = "America/Mexico_City"
ADMIN_PASSWORD = "cambia_esto"
```

Para contraseña de admin más segura, genera el hash primero:
```bash
python tools/hash_password.py "tu_password_seguro"
```
Luego usa `ADMIN_PASSWORD_HASH` en lugar de `ADMIN_PASSWORD`:
```toml
ADMIN_PASSWORD_HASH = "pbkdf2_sha256$260000$..."
```

### 3. Sin Supabase (modo local)
La app usa `data/quinela_data.json` automáticamente.
**Limitación:** en Streamlit Cloud el filesystem es efímero. Los datos se 
pierden si el servidor se reinicia (ocurre tras ~1h de inactividad).
Para un torneo de varios días, usa Supabase.

### 4. Con Supabase (recomendado para producción)
1. Crea proyecto en [supabase.com](https://supabase.com)
2. Ejecuta `supabase_schema.sql` en el SQL Editor
3. Instala la dependencia:
   ```bash
   pip install -r requirements.txt -r requirements-supabase.txt
   ```
   En Streamlit Cloud, **renombra** `requirements-supabase.txt` como
   `requirements.txt` o agrégalo al archivo principal.
4. Añade a los Secrets:
   ```toml
   SUPABASE_URL              = "https://TU-PROYECTO.supabase.co"
   SUPABASE_SERVICE_ROLE_KEY = "TU_SERVICE_ROLE_KEY"
   ```

## Ejecución local

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt   # sin supabase
# o:
pip install -r requirements.txt -r requirements-supabase.txt

streamlit run app.py
```

## Sistema de puntos

| Resultado         | Puntos |
|-------------------|--------|
| Marcador exacto   | 3      |
| Resultado correcto| 1      |
| Fallo             | 0      |

**Tiebreaker** (orden de desempate): Puntos → Exactos → Acertados →
Menor diferencia de goles → Mayor cantidad pronosticada.

## Calendario y bloqueos

- `kickoff_at` está lleno en formato ISO con offset `-06:00` (CDMX).
  El bloqueo automático actúa en cuanto llega esa hora.
- Si necesitas bloquear antes (e.g. partido adelantado), usa el panel
  de administración → **Bloqueos manuales**.
- Para actualizar horarios, edita `matches_2026.csv` y haz commit.
