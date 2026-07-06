-- 组合管理云端存储。请在 Supabase SQL Editor 中完整执行。

create table if not exists public.portfolios (
  id text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, name)
);

alter table public.portfolios enable row level security;
grant select, insert, update, delete on public.portfolios to authenticated;

drop policy if exists "Users manage own portfolios" on public.portfolios;
create policy "Users manage own portfolios"
on public.portfolios for all to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

create index if not exists portfolios_user_id_idx on public.portfolios(user_id);
