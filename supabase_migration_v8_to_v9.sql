-- Migración v8 -> v9.
-- Agrega pronósticos especiales, resultados oficiales de premios y sus índices.

create table if not exists public.quinela_special_predictions (
  username text not null references public.quinela_users(username) on delete cascade,
  category text not null,
  value text not null default '',
  updated_at timestamptz not null default now(),
  primary key (username, category)
);

create table if not exists public.quinela_special_results (
  category text primary key,
  value text not null default '',
  points integer not null default 5 check (points >= 0 and points <= 50),
  updated_at timestamptz not null default now()
);

create index if not exists idx_quinela_special_predictions_category on public.quinela_special_predictions(category);
create index if not exists idx_quinela_special_results_updated on public.quinela_special_results(updated_at desc);

alter table public.quinela_special_predictions enable row level security;
alter table public.quinela_special_results enable row level security;
