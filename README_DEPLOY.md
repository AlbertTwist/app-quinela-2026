# Quinela Mundial 2026 · Posgrado IMP — v9 tablas por etapa + premios

Versión reforzada para GitHub + Streamlit Cloud + Supabase, con diseño institucional, calendario completo de 104 partidos y dos tablas de competencia: **fase de grupos** y **eliminatorias**.

## Archivos principales

```text
app.py                         ← App principal
matches_2026.csv               ← Calendario completo M001–M104
requirements.txt               ← Dependencias de Streamlit Cloud, incluido Supabase
supabase_schema.sql            ← Esquema completo para instalación nueva
supabase_migration_v8_to_v9.sql← Migración si ya usabas v8
supabase_migration_v3_to_v4.sql← Migración histórica de auditoría/índices
tools/hash_password.py         ← Genera ADMIN_PASSWORD_HASH seguro
data/.gitkeep                  ← Mantiene carpeta data/ para modo local
.streamlit/config.toml         ← Tema visual
.gitignore                     ← Evita subir secrets y datos locales
```

## Qué cambió en v9

- La antigua tabla general se convierte en **Tablas y Premios**.
- Ranking separado para:
  - **Fase de grupos**: solo M001–M072.
  - **Eliminatorias**: M073–M104 + bonus de premios especiales.
  - **Global**: referencia acumulada de ambas etapas.
- Distinciones automáticas de fase de grupos:
  - Más marcadores exactos.
  - Más resultados acertados.
  - Mayor efectividad.
  - Mejor diferencia acumulada de marcador.
  - Mayor participación.
  - Mejor promedio.
- Pronósticos especiales de segunda etapa / torneo:
  - Campeón.
  - Subcampeón.
  - Tercer lugar.
  - Balón de Oro.
  - Bota de Oro.
  - Guante de Oro.
  - Mejor jugador joven.
  - Premio Fair Play.
  - Caballo negro.
- Nuevo panel admin para cargar ganadores oficiales de premios especiales.
- Exportación CSV de pronósticos especiales.

## Supabase

### Instalación nueva

1. Crea proyecto en Supabase.
2. Abre **SQL Editor**.
3. Ejecuta todo el contenido de `supabase_schema.sql`.
4. Copia `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` a los Secrets de Streamlit.
5. Reinicia/redeploy la app.

### Actualización desde v8

Si ya tienes v8 funcionando, ejecuta en Supabase **solo**:

```text
supabase_migration_v8_to_v9.sql
```

Después sube/reemplaza en GitHub:

```text
app.py
README_DEPLOY.md
requirements.txt
supabase_schema.sql
supabase_migration_v8_to_v9.sql
.streamlit/config.toml
```

No hace falta borrar datos previos.

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
POINTS_SPECIAL = 5
ENABLE_REGISTRATION = true
```

Puedes generar el hash de admin con:

```bash
python tools/hash_password.py "tu_password_seguro"
```

También funciona `ADMIN_PASSWORD = "..."`, pero `ADMIN_PASSWORD_HASH` es preferible.

## Sistema de puntos

| Concepto | Puntos por defecto |
|---|---:|
| Marcador exacto | 3 |
| Resultado correcto | 1 |
| Fallo | 0 |
| Premio especial acertado | 5 |

El valor de los premios especiales puede cambiarse con `POINTS_SPECIAL` o directamente al publicar cada premio desde Administración.

## Desempates

En cada tabla se ordena por:

1. Puntos.
2. Marcadores exactos.
3. Resultados acertados.
4. Premios especiales acertados, cuando aplique.
5. Menor diferencia total de marcador.
6. Mayor número de pronósticos.

## Eliminatorias

Las eliminatorias se cargan con placeholders, por ejemplo:

```text
Ganador Grupo A vs 3.º Grupo C/E/F/H/I
Ganador M073 vs Ganador M075
```

Cuando se definan los clasificados, actualiza `matches_2026.csv` reemplazando esos textos por los equipos reales y haz redeploy. No se requiere migración de base de datos porque todos los pronósticos, resultados y bloqueos se guardan por `match_id`.

En esta versión los `kickoff_at` de eliminatorias están vacíos para evitar bloqueos automáticos con horarios dudosos. El administrador puede bloquear manualmente desde **Administración → Bloqueos manuales**. Si deseas bloqueo automático, llena `kickoff_at` en formato ISO, por ejemplo:

```text
2026-07-19T13:00:00-06:00
```

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

## Notas operativas

- No subas `.streamlit/secrets.toml`, `.env`, `.env.local` ni `data/quinela_data.json`.
- Para cerrar registros cuando empiece el torneo, pon `ENABLE_REGISTRATION = false` en Secrets.
- Si cambia un horario, edita `matches_2026.csv`, confirma `kickoff_at` y redeploy.
- Para eliminatorias, actualiza los placeholders cuando estén definidos los clasificados.
