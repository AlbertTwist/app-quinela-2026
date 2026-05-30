# Quinela Mundial 2026 · Posgrado IMP — v8 dos etapas

Versión reforzada para GitHub + Streamlit Cloud + Supabase, con diseño institucional y calendario completo de 104 partidos: fase de grupos y eliminatorias hasta la final.

## Archivos principales

```text
app.py                    ← App principal
matches_2026.csv          ← Calendario completo M001–M104
requirements.txt          ← Dependencias de Streamlit Cloud, incluido Supabase
supabase_schema.sql       ← Tablas de Supabase, incluida auditoría
tools/hash_password.py    ← Genera ADMIN_PASSWORD_HASH seguro
data/.gitkeep             ← Mantiene carpeta data/ para modo local
.streamlit/config.toml    ← Tema visual
.gitignore                ← Evita subir secrets y datos locales
```

## Qué cambió en v8

- Se agregan **dos etapas**: fase de grupos y eliminatorias.
- `matches_2026.csv` ahora incluye **104 partidos**:
  - M001–M072: fase de grupos.
  - M073–M088: 16avos / Round of 32.
  - M089–M096: octavos.
  - M097–M100: cuartos.
  - M101–M102: semifinales.
  - M103: tercer lugar.
  - M104: final.
- Nueva pestaña **Eliminatorias** con tablero visual tipo bracket.
- Filtros por **Etapa** y **Grupo/Ronda** en pronósticos y resultados.
- Avance del usuario separado por etapa.
- Ranking global acumulado para todos los partidos cargados.
- Panel admin actualizado para publicar resultados y bloqueos por grupo/ronda.

## Importante sobre eliminatorias

Las eliminatorias se cargan con placeholders, por ejemplo:

```text
Ganador Grupo A vs 3.º Grupo C/E/F/H/I
Ganador M073 vs Ganador M075
```

Cuando se definan los clasificados, puedes actualizar `matches_2026.csv` reemplazando esos textos por los equipos reales y hacer redeploy. No se requiere migración de base de datos porque todos los pronósticos, resultados y bloqueos se guardan por `match_id`.

En esta versión los `kickoff_at` de eliminatorias están vacíos para evitar bloqueos automáticos con horarios dudosos. El administrador puede bloquear manualmente desde la pestaña **Administración → Bloqueos manuales**. Si deseas bloqueo automático, llena `kickoff_at` en formato ISO, por ejemplo:

```text
2026-07-19T13:00:00-06:00
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
3. Ejecuta todo el contenido de `supabase_schema.sql` si es una instalación nueva.
4. Copia `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` a los Secrets de Streamlit.
5. Reinicia/redeploy la app.

Si ya tienes v5/v6/v7 funcionando, normalmente **no necesitas migración nueva** para v8. El calendario crece a M104, pero la base ya acepta cualquier `match_id`.

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

## Actualización desde v7

Reemplaza/sube estos archivos:

```text
app.py
matches_2026.csv
README_DEPLOY.md
requirements.txt
.streamlit/config.toml
```

No subas secretos ni datos locales.

## Notas operativas

- No subas `.streamlit/secrets.toml`, `.env`, `.env.local` ni `data/quinela_data.json`.
- Para cerrar registros cuando empiece el torneo, pon `ENABLE_REGISTRATION = false` en Secrets.
- Si cambia un horario, edita `matches_2026.csv`, confirma `kickoff_at` y redeploy.
- Para eliminatorias, actualiza los placeholders cuando estén definidos los clasificados.
