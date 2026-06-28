-- Migración v13 -> v14
-- Agrega campos para etapa de eliminatorias:
--   Pronóstico: ganador de la llave y si se define en penales.
--   Resultado: ganador oficial de la llave y si se definió en penales.

alter table public.quinela_predictions
  add column if not exists predicted_winner text,
  add column if not exists predicted_penalties boolean not null default false;

alter table public.quinela_results
  add column if not exists official_winner text,
  add column if not exists decided_by_penalties boolean not null default false;

-- Valores esperados: 'home', 'away' o null/cadena vacía.
-- Se dejan permisivos para no romper datos históricos; la app normaliza valores vacíos.
create index if not exists idx_quinela_predictions_match_winner
  on public.quinela_predictions(match_id, predicted_winner);

create index if not exists idx_quinela_results_official_winner
  on public.quinela_results(official_winner);
