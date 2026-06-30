# Quinela Mundial 2026 · v14.4

Versión v14.4 con etapas independientes y regla final refinada para eliminatorias.

## Cambios clave

- La tabla de **grupos** y la tabla de **eliminatorias** se mantienen separadas.
- Nuevos usuarios pueden incorporarse en eliminatorias sin afectar la tabla de grupos.
- En eliminatorias:
  - Si el marcador **no es empate**, el ganador se deriva del marcador y se asume en tiempo regular o agregado.
  - Si el marcador **es empate**, el usuario debe elegir quién gana la llave.
  - Un marcador empatado se interpreta como definición en penales.

## Puntuación eliminatorias

Primero se evalúa si el usuario acertó **quién avanza**. Solo si acierta esa condición puede acceder a puntos extra.

- Ganador correcto con vía correcta: **2 pts**.
- Ganador correcto con vía distinta: **1 pt**.
  - Ejemplo: avanzó en regular/extra, pero el usuario puso penales.
  - Ejemplo: avanzó en penales, pero el usuario puso regular/extra.
- Marcador exacto: **+1 pt**, solo si también acertó quién avanza.
- Penales correctos: **+1 pt**, solo si oficialmente fue por penales, el usuario lo indicó y acertó quién avanza.
- Máximo por partido: **4 pts**.

Ejemplo de control:

- Oficial: 1–1, pasa Equipo A en penales.
- Usuario: 1–1, pasa Equipo B en penales.
- Resultado: **0 pts**, aunque haya acertado marcador e instancia, porque falló quién avanza.

No requiere migración nueva si ya ejecutaste la migración v14.
