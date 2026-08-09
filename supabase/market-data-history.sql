-- 恒生综合指数成分、证监会空头持仓与港股通历史持仓。
-- 本文件需要在 Supabase SQL Editor 中执行一次。

create table if not exists public.market_securities (
  stock_code text primary key check (stock_code ~ '^[0-9]{5}$'),
  name_zh text,
  name_en text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.market_index_constituents (
  index_code text not null,
  snapshot_date date not null,
  stock_code text not null references public.market_securities(stock_code) on delete cascade,
  constituent_name text,
  source_url text not null,
  ingested_at timestamptz not null default now(),
  primary key (index_code, snapshot_date, stock_code)
);

create table if not exists public.hk_short_positions_weekly (
  stock_code text not null references public.market_securities(stock_code) on delete cascade,
  report_date date not null,
  short_shares bigint not null check (short_shares >= 0),
  short_value_hkd numeric(24, 2) not null check (short_value_hkd >= 0),
  issued_shares bigint check (issued_shares > 0),
  short_ratio_pct numeric(14, 8) check (short_ratio_pct >= 0),
  ratio_quality text not null default 'missing_denominator'
    check (ratio_quality in ('official', 'licensed_vendor', 'missing_denominator')),
  source_url text not null,
  ingested_at timestamptz not null default now(),
  primary key (stock_code, report_date),
  check (
    (issued_shares is null and short_ratio_pct is null and ratio_quality = 'missing_denominator')
    or
    (issued_shares is not null and short_ratio_pct is not null and ratio_quality <> 'missing_denominator')
  )
);

create table if not exists public.hk_stock_connect_holdings_daily (
  stock_code text not null references public.market_securities(stock_code) on delete cascade,
  holding_date date not null,
  sh_holding_shares bigint check (sh_holding_shares >= 0),
  sz_holding_shares bigint check (sz_holding_shares >= 0),
  total_holding_shares bigint check (total_holding_shares >= 0),
  issued_shares bigint check (issued_shares > 0),
  holding_ratio_pct numeric(14, 8) check (holding_ratio_pct >= 0),
  completeness text not null
    check (completeness in ('complete', 'partial_sh', 'partial_sz', 'official_aggregate')),
  ratio_quality text not null default 'missing_denominator'
    check (ratio_quality in ('official', 'licensed_vendor', 'missing_denominator')),
  sh_source_url text,
  sz_source_url text,
  aggregate_source_url text,
  source_reported_ratio_pct numeric(14, 8) check (source_reported_ratio_pct >= 0),
  ingested_at timestamptz not null default now(),
  primary key (stock_code, holding_date),
  check (
    (completeness = 'complete' and sh_holding_shares is not null and sz_holding_shares is not null and total_holding_shares = sh_holding_shares + sz_holding_shares)
    or
    (completeness = 'partial_sh' and sh_holding_shares is not null and sz_holding_shares is null and total_holding_shares is null)
    or
    (completeness = 'partial_sz' and sh_holding_shares is null and sz_holding_shares is not null and total_holding_shares is null)
    or
    (completeness = 'official_aggregate' and sh_holding_shares is null and sz_holding_shares is null
      and total_holding_shares is not null and aggregate_source_url is not null)
  ),
  check (
    (issued_shares is null and holding_ratio_pct is null and ratio_quality = 'missing_denominator')
    or
    (issued_shares is not null and holding_ratio_pct is not null and ratio_quality <> 'missing_denominator')
  )
);

create table if not exists public.hk_market_insight_metrics_weekly (
  index_code text not null check (index_code in ('HSTECH', 'HSLI', 'HSMI', 'HSSI')),
  stock_code text not null references public.market_securities(stock_code) on delete cascade,
  week_date date not null,
  close_price numeric(20, 6) not null check (close_price > 0),
  bias_5w_pct numeric(14, 8),
  bias_30w_pct numeric(14, 8),
  bias_40w_pct numeric(14, 8),
  bias_50w_pct numeric(14, 8),
  percentile_5w_2y numeric(14, 8) check (percentile_5w_2y between 0 and 100),
  percentile_30w_2y numeric(14, 8) check (percentile_30w_2y between 0 and 100),
  percentile_40w_2y numeric(14, 8) check (percentile_40w_2y between 0 and 100),
  percentile_50w_2y numeric(14, 8) check (percentile_50w_2y between 0 and 100),
  five_week_return_pct numeric(14, 8),
  index_five_week_return_pct numeric(14, 8),
  excess_five_week_return_pct numeric(14, 8),
  index_return_quality text not null default 'official_index'
    check (index_return_quality in ('official_index', 'constituent_equal_weight')),
  price_source text not null default 'tencent_weekly',
  calculated_at timestamptz not null default now(),
  primary key (index_code, stock_code, week_date)
);

create table if not exists public.market_data_ingestion_runs (
  id uuid primary key default gen_random_uuid(),
  dataset text not null check (dataset in ('hsci_constituents', 'short_positions', 'stock_connect')),
  range_start date,
  range_end date,
  status text not null check (status in ('success', 'partial', 'failed')),
  rows_written integer not null default 0 check (rows_written >= 0),
  details jsonb not null default '{}'::jsonb,
  started_at timestamptz not null,
  finished_at timestamptz not null default now()
);

alter table public.market_data_ingestion_runs
  drop constraint if exists market_data_ingestion_runs_dataset_check;
alter table public.market_data_ingestion_runs
  add constraint market_data_ingestion_runs_dataset_check
  check (dataset in ('hsci_constituents', 'short_positions', 'stock_connect', 'weekly_metrics'));

create index if not exists market_index_constituents_latest_idx
  on public.market_index_constituents(index_code, snapshot_date desc);
create index if not exists hk_short_positions_date_idx
  on public.hk_short_positions_weekly(report_date desc, stock_code);
create index if not exists hk_stock_connect_holdings_date_idx
  on public.hk_stock_connect_holdings_daily(holding_date desc, stock_code);
create index if not exists hk_market_insight_metrics_latest_idx
  on public.hk_market_insight_metrics_weekly(index_code, week_date desc, stock_code);
create index if not exists market_data_ingestion_runs_dataset_idx
  on public.market_data_ingestion_runs(dataset, finished_at desc);

alter table public.market_securities enable row level security;
alter table public.market_index_constituents enable row level security;
alter table public.hk_short_positions_weekly enable row level security;
alter table public.hk_stock_connect_holdings_daily enable row level security;
alter table public.hk_market_insight_metrics_weekly enable row level security;
alter table public.market_data_ingestion_runs enable row level security;

grant select on public.market_securities to authenticated;
grant select on public.market_index_constituents to authenticated;
grant select on public.hk_short_positions_weekly to authenticated;
grant select on public.hk_stock_connect_holdings_daily to authenticated;
grant select on public.hk_market_insight_metrics_weekly to authenticated;
grant select on public.market_data_ingestion_runs to authenticated;

grant select, insert, update, delete on public.market_securities to service_role;
grant select, insert, update, delete on public.market_index_constituents to service_role;
grant select, insert, update, delete on public.hk_short_positions_weekly to service_role;
grant select, insert, update, delete on public.hk_stock_connect_holdings_daily to service_role;
grant select, insert, update, delete on public.hk_market_insight_metrics_weekly to service_role;
grant select, insert, update, delete on public.market_data_ingestion_runs to service_role;

drop policy if exists "Authenticated users read market securities" on public.market_securities;
create policy "Authenticated users read market securities"
on public.market_securities for select to authenticated using (true);

drop policy if exists "Authenticated users read index constituents" on public.market_index_constituents;
create policy "Authenticated users read index constituents"
on public.market_index_constituents for select to authenticated using (true);

drop policy if exists "Authenticated users read short positions" on public.hk_short_positions_weekly;
create policy "Authenticated users read short positions"
on public.hk_short_positions_weekly for select to authenticated using (true);

drop policy if exists "Authenticated users read stock connect holdings" on public.hk_stock_connect_holdings_daily;
create policy "Authenticated users read stock connect holdings"
on public.hk_stock_connect_holdings_daily for select to authenticated using (true);

drop policy if exists "Authenticated users read weekly market insight metrics" on public.hk_market_insight_metrics_weekly;
create policy "Authenticated users read weekly market insight metrics"
on public.hk_market_insight_metrics_weekly for select to authenticated using (true);

drop policy if exists "Authenticated users read ingestion runs" on public.market_data_ingestion_runs;
create policy "Authenticated users read ingestion runs"
on public.market_data_ingestion_runs for select to authenticated using (true);

create or replace view public.current_market_index_constituents
with (security_invoker = true)
as
select c.index_code, c.snapshot_date, c.stock_code, c.constituent_name, c.source_url
from public.market_index_constituents c
where c.snapshot_date = (
  select max(latest.snapshot_date)
  from public.market_index_constituents latest
  where latest.index_code = c.index_code
);

create or replace view public.hsci_current_short_history
with (security_invoker = true)
as
select s.stock_code, q.name_zh, q.name_en, s.report_date, s.short_shares,
       s.short_value_hkd, s.issued_shares, s.short_ratio_pct, s.ratio_quality,
       s.source_url, s.ingested_at
from public.hk_short_positions_weekly s
join public.market_securities q on q.stock_code = s.stock_code
join public.current_market_index_constituents c
  on c.index_code = 'HSCI' and c.stock_code = s.stock_code;

create or replace view public.hsci_current_stock_connect_history
with (security_invoker = true)
as
select h.stock_code, q.name_zh, q.name_en, h.holding_date,
       h.sh_holding_shares, h.sz_holding_shares, h.total_holding_shares,
       h.issued_shares, h.holding_ratio_pct, h.completeness, h.ratio_quality,
       h.sh_source_url, h.sz_source_url, h.aggregate_source_url,
       h.source_reported_ratio_pct, h.ingested_at
from public.hk_stock_connect_holdings_daily h
join public.market_securities q on q.stock_code = h.stock_code
join public.current_market_index_constituents c
  on c.index_code = 'HSCI' and c.stock_code = h.stock_code;

grant select on public.current_market_index_constituents to authenticated;
grant select on public.hsci_current_short_history to authenticated;
grant select on public.hsci_current_stock_connect_history to authenticated;

create or replace view public.current_hk_market_insight_metrics
with (security_invoker = true)
as
select distinct on (m.index_code, m.stock_code)
       m.index_code, m.stock_code, m.week_date, m.close_price,
       m.bias_5w_pct, m.bias_30w_pct, m.bias_40w_pct, m.bias_50w_pct,
       m.percentile_5w_2y, m.percentile_30w_2y,
       m.percentile_40w_2y, m.percentile_50w_2y,
       m.five_week_return_pct, m.index_five_week_return_pct,
       m.excess_five_week_return_pct, m.index_return_quality, m.calculated_at
from public.hk_market_insight_metrics_weekly m
order by m.index_code, m.stock_code, m.week_date desc;

grant select on public.current_hk_market_insight_metrics to authenticated;
