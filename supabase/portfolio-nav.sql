-- 基金份额、资金流水、日终净值与基准快照。

create extension if not exists pg_cron;
create extension if not exists pg_net;

create table if not exists public.portfolio_cash_flows (
  id uuid primary key default gen_random_uuid(),
  portfolio_id text not null references public.portfolios(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  flow_type text not null check (flow_type in ('subscription', 'redemption')),
  currency text not null check (currency in ('CNY', 'HKD', 'USD')),
  amount numeric not null check (amount > 0),
  nav_before numeric not null check (nav_before > 0),
  units_changed numeric not null check (units_changed > 0),
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.portfolio_daily_nav (
  portfolio_id text not null references public.portfolios(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  nav_date date not null,
  base_currency text not null check (base_currency in ('CNY', 'USD')),
  total_assets numeric not null,
  total_units numeric not null check (total_units > 0),
  unit_nav numeric not null check (unit_nav > 0),
  cash_value numeric not null,
  position_value numeric not null,
  fx_rates jsonb not null default '{}'::jsonb,
  price_status jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (portfolio_id, nav_date)
);

create table if not exists public.benchmark_daily_close (
  benchmark_code text not null,
  trade_date date not null,
  close_value numeric not null check (close_value > 0),
  currency text not null,
  source text not null,
  created_at timestamptz not null default now(),
  primary key (benchmark_code, trade_date)
);

alter table public.portfolio_cash_flows enable row level security;
alter table public.portfolio_daily_nav enable row level security;
alter table public.benchmark_daily_close enable row level security;

grant select, insert on public.portfolio_cash_flows to authenticated;
grant select on public.portfolio_daily_nav to authenticated;
grant select on public.benchmark_daily_close to authenticated;
grant select, insert, update on public.portfolio_daily_nav to service_role;
grant select, insert, update on public.benchmark_daily_close to service_role;

create policy "Users manage own portfolio cash flows" on public.portfolio_cash_flows
for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "Users read own daily nav" on public.portfolio_daily_nav
for select to authenticated using (user_id = auth.uid());
create policy "Authenticated users read benchmarks" on public.benchmark_daily_close
for select to authenticated using (true);

create index if not exists portfolio_cash_flows_portfolio_idx on public.portfolio_cash_flows(portfolio_id, occurred_at);
create index if not exists portfolio_daily_nav_user_date_idx on public.portfolio_daily_nav(user_id, nav_date);
