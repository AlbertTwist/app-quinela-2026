-- Ejecutar en Supabase SQL Editor.
-- Backend para Quinela Mundial 2026 · Posgrado IMP — v4.

create table if not exists public.quinela_users (
  username text primary key,
  display_name text,
  password_hash text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.quinela_predictions (
  username text not null references public.quinela_users(username) on delete cascade,
  match_id text not null,
  home_goals integer not null check (home_goals >= 0 and home_goals <= 30),
  away_goals integer not null check (away_goals >= 0 and away_goals <= 30),
  updated_at timestamptz not null default now(),
  primary key (username, match_id)
);

create table if not exists public.quinela_results (
  match_id text primary key,
  home_goals integer not null check (home_goals >= 0 and home_goals <= 30),
  away_goals integer not null check (away_goals >= 0 and away_goals <= 30),
  updated_at timestamptz not null default now()
);

create table if not exists public.quinela_locks (
  match_id text primary key,
  locked boolean not null default false,
  updated_at timestamptz not null default now()
);

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

-- Recomendado: mantener RLS activo y usar la SERVICE_ROLE_KEY solo en Streamlit Secrets.
alter table public.quinela_users enable row level security;
alter table public.quinela_predictions enable row level security;
alter table public.quinela_results enable row level security;
alter table public.quinela_locks enable row level security;
alter table public.quinela_audit_log enable row level security;
