# Quinela Mundial 2026 · Posgrado IMP — v11 operación + diseño

Versión reforzada para GitHub + Streamlit Cloud + Supabase. Mantiene las dos etapas de competencia (**fase de grupos** y **eliminatorias**) y agrega mejoras operativas para administración, seguridad y respaldo.

## Archivos principales

```text
app.py                         ← App principal
matches_2026.csv               ← Calendario completo M001–M104
requirements.txt               ← Dependencias de Streamlit Cloud, incluido Supabase
supabase_schema.sql            ← Esquema completo para instalación nueva
supabase_migration_v8_to_v9.sql← Migración si vienes de v8
supabase_migration_v3_to_v4.sql← Migración histórica de auditoría/índices
tools/hash_password.py         ← Genera ADMIN_PASSWORD_HASH seguro
data/.gitkeep                  ← Mantiene carpeta data/ para modo local
.streamlit/config.toml         ← Tema visual
.gitignore                     ← Evita subir secrets y datos locales
```

## Qué cambió en v11

- Cambio de contraseña desde la sesión del usuario.
- Código opcional de invitación para registros nuevos.
- Diagnóstico de despliegue en el panel de administración.
- Exportación completa en ZIP: respaldo JSON, calendario, tablas y pronósticos.
- Normalización robusta de premios especiales: acentos, mayúsculas, espacios y signos ya no afectan coincidencias simples; por ejemplo, `Mexico` y `México` se evalúan igual.
- Limpieza de encabezados y documentación para evitar confusión entre versiones.

## Funciones heredadas de v9/v10

- Tabla separada para **fase de grupos**: M001–M072.
- Tabla separada para **eliminatorias**: M073–M104 + bonus de premios especiales.
- Tabla global acumulada como referencia.
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
- Panel admin para resultados, bloqueos, premios, participantes, cobertura, auditoría y respaldos.

## Supabase

### Instalación nueva

1. Crea proyecto en Supabase.
2. Abre **SQL Editor**.
3. Ejecuta todo el contenido de `supabase_schema.sql`.
4. Copia `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` a los Secrets de Streamlit.
5. Reinicia/redeploy la app.

### Actualización desde v8/v9/v10

Si ya ejecutaste la migración de v9, no necesitas otra migración para v11. Solo reemplaza archivos en GitHub.

Si vienes directamente desde v8, ejecuta primero:

```text
supabase_migration_v8_to_v9.sql
```

Después sube/reemplaza:

```text
app.py
README_DEPLOY.md
requirements.txt
.streamlit/config.toml
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
POINTS_SPECIAL = 5
ENABLE_REGISTRATION = true
REGISTRATION_INVITE_CODE = "codigo_privado_opcional"
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
- Para permitir registros solo por invitación, define `REGISTRATION_INVITE_CODE`.
- Si cambia un horario, edita `matches_2026.csv`, confirma `kickoff_at` y redeploy.
- Usa **Administración → Diagnóstico** para verificar backend, calendario, registro y configuración general.


## v12 · mejoras finales de estabilidad

Esta versión agrega cambios pequeños pero útiles para operación en vivo:

- Caché de calendario sensible a cambios de `matches_2026.csv`.
- Corrección de CSS de tarjetas laterales.
- Llaves únicas adicionales en formularios para evitar colisiones de widgets.
- Secret opcional `READ_ONLY_MODE = true` para poner la app en modo consulta durante mantenimiento.
- `runtime.txt` para fijar Python 3.12 en despliegues compatibles.
- `.gitignore` para evitar subir secretos, respaldos o datos locales.

Secret opcional nuevo:

```toml
READ_ONLY_MODE = false
```
