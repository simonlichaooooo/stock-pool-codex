-- 市场洞察周线指标持久化迁移；在 Supabase SQL Editor 中执行一次。

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

create index if not exists hk_market_insight_metrics_latest_idx
  on public.hk_market_insight_metrics_weekly(index_code, week_date desc, stock_code);

alter table public.hk_market_insight_metrics_weekly enable row level security;

grant select on public.hk_market_insight_metrics_weekly to authenticated;
grant select, insert, update, delete on public.hk_market_insight_metrics_weekly to service_role;

drop policy if exists "Authenticated users read weekly market insight metrics"
  on public.hk_market_insight_metrics_weekly;
create policy "Authenticated users read weekly market insight metrics"
on public.hk_market_insight_metrics_weekly for select to authenticated using (true);

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

alter table public.market_data_ingestion_runs
  drop constraint if exists market_data_ingestion_runs_dataset_check;
alter table public.market_data_ingestion_runs
  add constraint market_data_ingestion_runs_dataset_check
  check (dataset in ('hsci_constituents', 'short_positions', 'stock_connect', 'weekly_metrics'));
