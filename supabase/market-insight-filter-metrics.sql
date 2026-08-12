-- 市场洞察自定义筛选指标扩展。
--
-- 目标：
-- 1. 持久化 HSTECH/HSLI/HSMI/HSSI 指数周线，避免浏览器临时请求指数行情；
-- 2. 预计算 5/10/20/30/40/50 周乖离率、速度、1 年/2 年分位值；
-- 3. 预计算 1 周和 5 周股票/指数/超额收益；
-- 4. 提供可直接被 PostgREST 组合筛选的当前指标视图和覆盖率视图。
--
-- 本文件是幂等迁移，可在 Supabase SQL Editor 中整体执行一次。

begin;

create table if not exists public.market_index_weekly_prices (
  index_code text not null check (index_code in ('HSTECH', 'HSLI', 'HSMI', 'HSSI')),
  week_date date not null,
  close_price numeric(20, 6) not null check (close_price > 0),
  price_source text not null default 'eastmoney_index_weekly',
  ingested_at timestamptz not null default now(),
  primary key (index_code, week_date)
);

create index if not exists market_index_weekly_prices_latest_idx
  on public.market_index_weekly_prices(index_code, week_date desc);

alter table public.market_index_weekly_prices enable row level security;
grant select on public.market_index_weekly_prices to authenticated;
grant select, insert, update, delete on public.market_index_weekly_prices to service_role;

drop policy if exists "Authenticated users read market index weekly prices"
  on public.market_index_weekly_prices;
create policy "Authenticated users read market index weekly prices"
on public.market_index_weekly_prices for select to authenticated using (true);

alter table public.hk_market_insight_metrics_weekly
  add column if not exists bias_10w_pct numeric(14, 8),
  add column if not exists bias_20w_pct numeric(14, 8),
  add column if not exists bias_speed_5w_pct numeric(14, 8),
  add column if not exists bias_speed_10w_pct numeric(14, 8),
  add column if not exists bias_speed_20w_pct numeric(14, 8),
  add column if not exists bias_speed_30w_pct numeric(14, 8),
  add column if not exists bias_speed_40w_pct numeric(14, 8),
  add column if not exists bias_speed_50w_pct numeric(14, 8),
  add column if not exists percentile_5w_1y numeric(14, 8) check (percentile_5w_1y between 0 and 100),
  add column if not exists percentile_10w_1y numeric(14, 8) check (percentile_10w_1y between 0 and 100),
  add column if not exists percentile_20w_1y numeric(14, 8) check (percentile_20w_1y between 0 and 100),
  add column if not exists percentile_30w_1y numeric(14, 8) check (percentile_30w_1y between 0 and 100),
  add column if not exists percentile_40w_1y numeric(14, 8) check (percentile_40w_1y between 0 and 100),
  add column if not exists percentile_50w_1y numeric(14, 8) check (percentile_50w_1y between 0 and 100),
  add column if not exists percentile_10w_2y numeric(14, 8) check (percentile_10w_2y between 0 and 100),
  add column if not exists percentile_20w_2y numeric(14, 8) check (percentile_20w_2y between 0 and 100),
  add column if not exists one_week_return_pct numeric(14, 8),
  add column if not exists index_one_week_return_pct numeric(14, 8),
  add column if not exists excess_one_week_return_pct numeric(14, 8);

-- 保持旧视图字段顺序不变，只在尾部追加字段，兼容已上线客户端。
create or replace view public.current_hk_market_insight_metrics
with (security_invoker = true)
as
select distinct on (m.index_code, m.stock_code)
       m.index_code, m.stock_code, m.week_date, m.close_price,
       m.bias_5w_pct, m.bias_30w_pct, m.bias_40w_pct, m.bias_50w_pct,
       m.percentile_5w_2y, m.percentile_30w_2y,
       m.percentile_40w_2y, m.percentile_50w_2y,
       m.five_week_return_pct, m.index_five_week_return_pct,
       m.excess_five_week_return_pct, m.index_return_quality, m.calculated_at,
       m.price_source,
       m.bias_10w_pct, m.bias_20w_pct,
       m.bias_speed_5w_pct, m.bias_speed_10w_pct, m.bias_speed_20w_pct,
       m.bias_speed_30w_pct, m.bias_speed_40w_pct, m.bias_speed_50w_pct,
       m.percentile_5w_1y, m.percentile_10w_1y, m.percentile_20w_1y,
       m.percentile_30w_1y, m.percentile_40w_1y, m.percentile_50w_1y,
       m.percentile_10w_2y, m.percentile_20w_2y,
       m.one_week_return_pct, m.index_one_week_return_pct,
       m.excess_one_week_return_pct
from public.hk_market_insight_metrics_weekly m
order by m.index_code, m.stock_code, m.week_date desc;

grant select on public.current_hk_market_insight_metrics to authenticated;

create or replace view public.current_hk_market_insight_filter_metrics
with (security_invoker = true)
as
select m.index_code, m.stock_code, m.week_date, m.close_price,
       m.bias_5w_pct, m.bias_10w_pct, m.bias_20w_pct,
       m.bias_30w_pct, m.bias_40w_pct, m.bias_50w_pct,
       m.bias_speed_5w_pct, m.bias_speed_10w_pct, m.bias_speed_20w_pct,
       m.bias_speed_30w_pct, m.bias_speed_40w_pct, m.bias_speed_50w_pct,
       m.percentile_5w_1y, m.percentile_10w_1y, m.percentile_20w_1y,
       m.percentile_30w_1y, m.percentile_40w_1y, m.percentile_50w_1y,
       m.percentile_5w_2y, m.percentile_10w_2y, m.percentile_20w_2y,
       m.percentile_30w_2y, m.percentile_40w_2y, m.percentile_50w_2y,
       m.one_week_return_pct, m.index_one_week_return_pct,
       m.excess_one_week_return_pct,
       m.five_week_return_pct, m.index_five_week_return_pct,
       m.excess_five_week_return_pct,
       m.index_return_quality, m.price_source, m.calculated_at
from public.current_hk_market_insight_metrics m;

grant select on public.current_hk_market_insight_filter_metrics to authenticated;

create or replace view public.hk_market_insight_filter_metric_coverage
with (security_invoker = true)
as
with history as (
  select index_code, stock_code, min(week_date) as first_week,
         max(week_date) as latest_week, count(*)::integer as stored_weeks
  from public.hk_market_insight_metrics_weekly
  group by index_code, stock_code
)
select m.index_code, m.stock_code, h.first_week, h.latest_week, h.stored_weeks,
       (m.bias_5w_pct is not null and m.bias_10w_pct is not null
        and m.bias_20w_pct is not null and m.bias_30w_pct is not null
        and m.bias_40w_pct is not null and m.bias_50w_pct is not null) as has_all_biases,
       (m.bias_speed_5w_pct is not null and m.bias_speed_10w_pct is not null
        and m.bias_speed_20w_pct is not null and m.bias_speed_30w_pct is not null
        and m.bias_speed_40w_pct is not null and m.bias_speed_50w_pct is not null) as has_all_speeds,
       (m.percentile_5w_1y is not null and m.percentile_10w_1y is not null
        and m.percentile_20w_1y is not null and m.percentile_30w_1y is not null
        and m.percentile_40w_1y is not null and m.percentile_50w_1y is not null) as has_all_1y_percentiles,
       (m.percentile_5w_2y is not null and m.percentile_10w_2y is not null
        and m.percentile_20w_2y is not null and m.percentile_30w_2y is not null
        and m.percentile_40w_2y is not null and m.percentile_50w_2y is not null) as has_all_2y_percentiles,
       (m.excess_one_week_return_pct is not null
        and m.excess_five_week_return_pct is not null) as has_standard_excess_returns,
       m.index_return_quality
from public.current_hk_market_insight_filter_metrics m
join history h using (index_code, stock_code);

grant select on public.hk_market_insight_filter_metric_coverage to authenticated;

create or replace view public.hk_market_insight_filter_coverage_summary
with (security_invoker = true)
as
select index_code, max(latest_week) as latest_week,
       count(*)::integer as stocks,
       count(*) filter (where has_all_biases)::integer as stocks_with_all_biases,
       count(*) filter (where has_all_speeds)::integer as stocks_with_all_speeds,
       count(*) filter (where has_all_1y_percentiles)::integer as stocks_with_all_1y_percentiles,
       count(*) filter (where has_all_2y_percentiles)::integer as stocks_with_all_2y_percentiles,
       count(*) filter (where has_standard_excess_returns)::integer as stocks_with_standard_excess_returns,
       count(*) filter (where index_return_quality = 'official_index')::integer as stocks_with_official_index_return
from public.hk_market_insight_filter_metric_coverage
group by index_code
order by index_code;

grant select on public.hk_market_insight_filter_coverage_summary to authenticated;

commit;
