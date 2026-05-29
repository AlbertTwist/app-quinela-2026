-- Ejecutar si ya tenías v3 en Supabase y solo quieres agregar auditoría/índices.

create table if not exists public.quinela_audit_log (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  actor text not null default 'system',
  event text not null,
  detail jsonb not null default '{}'::jsonb
);

create index if not exists idx_quinela_predictions_match on public.quinela_predictions(match_id);
create index if not exists idx_quinela_results_updated on public.quinela_results(updated_at desc);
create index if not exists idx_quinela_audit_created on public.quinela_audit_log(created_at desc);
create index if not exists idx_quinela_audit_event on public.quinela_audit_log(event);

alter table public.quinela_audit_log enable row level security;
