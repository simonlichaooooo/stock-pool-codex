-- 组合管理正式云端数据结构。
-- 在 Supabase SQL Editor 执行后，可将当前前端的本地持久化切换为 PostgREST。

create table if not exists public.portfolios (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  account_type text not null check (account_type in ('CNY', 'HKUS')),
  start_cny numeric not null default 0 check (start_cny >= 0),
  start_hkd numeric not null default 0 check (start_hkd >= 0),
  start_usd numeric not null default 0 check (start_usd >= 0),
  start_base numeric not null check (start_base > 0),
  cash_cny numeric not null default 0 check (cash_cny >= 0),
  cash_hkd numeric not null default 0 check (cash_hkd >= 0),
  cash_usd numeric not null default 0 check (cash_usd >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, name)
);

create table if not exists public.portfolio_positions (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references public.portfolios(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  code text not null,
  raw_code text,
  market text not null check (market in ('CN', 'HK', 'US')),
  exchange text,
  quote_id text,
  currency text not null check (currency in ('CNY', 'HKD', 'USD')),
  shares numeric not null check (shares > 0 and shares = trunc(shares)),
  average_cost numeric not null check (average_cost > 0),
  latest_price numeric not null default 0 check (latest_price >= 0),
  price_updated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (portfolio_id, market, code)
);

alter table public.portfolios enable row level security;
alter table public.portfolio_positions enable row level security;

grant select, insert, update, delete on public.portfolios to authenticated;
grant select, insert, update, delete on public.portfolio_positions to authenticated;

drop policy if exists "Users manage own portfolios" on public.portfolios;
create policy "Users manage own portfolios"
on public.portfolios for all to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

drop policy if exists "Users manage own portfolio positions" on public.portfolio_positions;
create policy "Users manage own portfolio positions"
on public.portfolio_positions for all to authenticated
using (
  user_id = auth.uid()
  and exists (
    select 1 from public.portfolios p
    where p.id = portfolio_id and p.user_id = auth.uid()
  )
)
with check (
  user_id = auth.uid()
  and exists (
    select 1 from public.portfolios p
    where p.id = portfolio_id and p.user_id = auth.uid()
  )
);

create index if not exists portfolios_user_id_idx on public.portfolios(user_id);
create index if not exists portfolio_positions_portfolio_id_idx on public.portfolio_positions(portfolio_id);
create index if not exists portfolio_positions_user_id_idx on public.portfolio_positions(user_id);
