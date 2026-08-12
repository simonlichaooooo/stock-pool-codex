-- 市场洞察第二阶段：月度超额收益与数据库原生复合筛选。
--
-- 目标：
-- 1. 持久化指数月线和个股月度超额收益，支持“当月”和“指定月份”；
-- 2. 将乖离率、速度、双口径分位值、超额收益及仓位变化统一放到数据库筛选；
-- 3. 任意多个已启用指标均按 AND 执行，缺失数据明确排除并返回缺失条件数。
--
-- 依赖：market-data-history.sql、market-insight-filter-metrics.sql。
-- 本文件是幂等迁移，可在 Supabase SQL Editor 中整体执行一次。

begin;

create table if not exists public.market_index_monthly_prices (
  index_code text not null check (index_code in ('HSTECH', 'HSLI', 'HSMI', 'HSSI')),
  month_start date not null,
  period_end date not null,
  close_price numeric(20, 6) not null check (close_price > 0),
  price_source text not null default 'eastmoney_index_monthly',
  ingested_at timestamptz not null default now(),
  primary key (index_code, month_start),
  check (date_trunc('month', period_end)::date = month_start)
);

create table if not exists public.hk_market_insight_monthly_returns (
  index_code text not null check (index_code in ('HSTECH', 'HSLI', 'HSMI', 'HSSI')),
  stock_code text not null references public.market_securities(stock_code) on delete cascade,
  month_start date not null,
  period_end date not null,
  close_price numeric(20, 6) not null check (close_price > 0),
  stock_return_pct numeric(14, 8),
  index_return_pct numeric(14, 8),
  excess_return_pct numeric(14, 8),
  index_return_quality text not null default 'official_index'
    check (index_return_quality in ('official_index', 'constituent_equal_weight')),
  price_source text not null default 'tencent_monthly',
  calculated_at timestamptz not null default now(),
  primary key (index_code, stock_code, month_start),
  check (date_trunc('month', period_end)::date = month_start)
);

create index if not exists market_index_monthly_prices_latest_idx
  on public.market_index_monthly_prices(index_code, month_start desc);
create index if not exists hk_market_insight_monthly_returns_latest_idx
  on public.hk_market_insight_monthly_returns(index_code, month_start desc, stock_code);
create index if not exists hk_market_insight_monthly_returns_stock_idx
  on public.hk_market_insight_monthly_returns(index_code, stock_code, month_start desc);

-- 现有索引以日期开头，以下两个索引专门服务每只股票的最新值/五周前值查询。
create index if not exists hk_short_positions_stock_date_idx
  on public.hk_short_positions_weekly(stock_code, report_date desc)
  where short_ratio_pct is not null;
create index if not exists hk_stock_connect_holdings_stock_date_idx
  on public.hk_stock_connect_holdings_daily(stock_code, holding_date desc)
  where holding_ratio_pct is not null and total_holding_shares is not null;

alter table public.market_index_monthly_prices enable row level security;
alter table public.hk_market_insight_monthly_returns enable row level security;

grant select on public.market_index_monthly_prices to authenticated;
grant select on public.hk_market_insight_monthly_returns to authenticated;
grant select, insert, update, delete on public.market_index_monthly_prices to service_role;
grant select, insert, update, delete on public.hk_market_insight_monthly_returns to service_role;

drop policy if exists "Authenticated users read market index monthly prices"
  on public.market_index_monthly_prices;
create policy "Authenticated users read market index monthly prices"
on public.market_index_monthly_prices for select to authenticated using (true);

drop policy if exists "Authenticated users read monthly market insight returns"
  on public.hk_market_insight_monthly_returns;
create policy "Authenticated users read monthly market insight returns"
on public.hk_market_insight_monthly_returns for select to authenticated using (true);

-- 每个指数/股票的当前周度指标，加上最新及五周前的仓位比例。
create or replace view public.current_hk_market_insight_filter_universe
with (security_invoker = true)
as
select m.*,
       latest_short.report_date as short_report_date,
       latest_short.short_ratio_pct,
       previous_short.report_date as short_previous_report_date,
       previous_short.short_ratio_pct as short_previous_ratio_pct,
       case when latest_short.short_ratio_pct is not null
                  and previous_short.short_ratio_pct is not null
            then latest_short.short_ratio_pct - previous_short.short_ratio_pct end
         as short_change_5w_pct,
       latest_connect.holding_date as connect_holding_date,
       latest_connect.holding_ratio_pct as connect_holding_ratio_pct,
       previous_connect.holding_date as connect_previous_holding_date,
       previous_connect.holding_ratio_pct as connect_previous_holding_ratio_pct,
       case when latest_connect.holding_ratio_pct is not null
                  and previous_connect.holding_ratio_pct is not null
            then latest_connect.holding_ratio_pct - previous_connect.holding_ratio_pct end
         as connect_change_5w_pct
from public.current_hk_market_insight_filter_metrics m
left join lateral (
  select s.report_date, s.short_ratio_pct
  from public.hk_short_positions_weekly s
  where s.stock_code = m.stock_code and s.short_ratio_pct is not null
  order by s.report_date desc
  limit 1
) latest_short on true
left join lateral (
  select s.report_date, s.short_ratio_pct
  from public.hk_short_positions_weekly s
  where s.stock_code = m.stock_code
    and s.short_ratio_pct is not null
    and s.report_date <= latest_short.report_date - 35
  order by s.report_date desc
  limit 1
) previous_short on true
left join lateral (
  select h.holding_date, h.holding_ratio_pct
  from public.hk_stock_connect_holdings_daily h
  where h.stock_code = m.stock_code
    and h.holding_ratio_pct is not null
    and h.total_holding_shares is not null
  order by h.holding_date desc
  limit 1
) latest_connect on true
left join lateral (
  select h.holding_date, h.holding_ratio_pct
  from public.hk_stock_connect_holdings_daily h
  where h.stock_code = m.stock_code
    and h.holding_ratio_pct is not null
    and h.total_holding_shares is not null
    and h.holding_date <= latest_connect.holding_date - 35
  order by h.holding_date desc
  limit 1
) previous_connect on true;

grant select on public.current_hk_market_insight_filter_universe to authenticated;

create or replace view public.hk_market_insight_monthly_coverage_summary
with (security_invoker = true)
as
select index_code,
       count(distinct stock_code)::integer as stocks,
       min(month_start) as first_month,
       max(month_start) as latest_month,
       count(*)::integer as stored_stock_months,
       count(*) filter (where excess_return_pct is not null)::integer
         as stock_months_with_excess_return,
       count(*) filter (where index_return_quality = 'official_index')::integer
         as stock_months_with_official_index_return
from public.hk_market_insight_monthly_returns
group by index_code
order by index_code;

grant select on public.hk_market_insight_monthly_coverage_summary to authenticated;

-- p_conditions 示例：
-- [{"metric":"percentile","span":"30","percentileWindow":"2y",
--   "operator":"lt","value":"20","month":""}]
-- 返回整个候选集合及每只股票的匹配结果，便于前端同时展示“匹配数”和“缺数据数”。
create or replace function public.filter_hk_market_insights(
  p_index_codes text[],
  p_conditions jsonb
)
returns table (
  index_code text,
  stock_code text,
  matches boolean,
  missing_condition_count integer
)
language sql
stable
security invoker
set search_path = public
as $$
with payload as (
  select case
           when jsonb_typeof(coalesce(p_conditions, '[]'::jsonb)) = 'array'
             then coalesce(p_conditions, '[]'::jsonb)
           else '[]'::jsonb
         end as conditions
),
conditions as (
  select item.ordinality::integer as condition_number,
         item.value ->> 'metric' as metric,
         item.value ->> 'span' as span,
         coalesce(item.value ->> 'percentileWindow', '2y') as percentile_window,
         item.value ->> 'month' as month_text,
         item.value ->> 'operator' as comparison_operator,
         case
           when coalesce(item.value ->> 'value', '')
                  ~ '^[-+]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
             then (item.value ->> 'value')::numeric
         end as expected_value
  from payload
  cross join lateral jsonb_array_elements(payload.conditions)
    with ordinality as item(value, ordinality)
),
universe as (
  select u.*
  from public.current_hk_market_insight_filter_universe u
  where u.index_code = any(coalesce(p_index_codes, array[]::text[]))
),
evaluated as (
  select u.index_code,
         u.stock_code,
         c.condition_number,
         c.comparison_operator,
         c.expected_value,
         case
           when c.metric = 'excess' and c.span = '1w'
             then u.excess_one_week_return_pct
           when c.metric = 'excess' and c.span = '5w'
             then u.excess_five_week_return_pct
           when c.metric = 'excess' and c.span in ('month', 'specific')
             then monthly.excess_return_pct
           when c.metric = 'bias' and c.span = '5' then u.bias_5w_pct
           when c.metric = 'bias' and c.span = '10' then u.bias_10w_pct
           when c.metric = 'bias' and c.span = '20' then u.bias_20w_pct
           when c.metric = 'bias' and c.span = '30' then u.bias_30w_pct
           when c.metric = 'bias' and c.span = '40' then u.bias_40w_pct
           when c.metric = 'bias' and c.span = '50' then u.bias_50w_pct
           when c.metric = 'speed' and c.span = '5' then u.bias_speed_5w_pct
           when c.metric = 'speed' and c.span = '10' then u.bias_speed_10w_pct
           when c.metric = 'speed' and c.span = '20' then u.bias_speed_20w_pct
           when c.metric = 'speed' and c.span = '30' then u.bias_speed_30w_pct
           when c.metric = 'speed' and c.span = '40' then u.bias_speed_40w_pct
           when c.metric = 'speed' and c.span = '50' then u.bias_speed_50w_pct
           when c.metric = 'percentile' and c.span = '5' and c.percentile_window = '1y'
             then u.percentile_5w_1y
           when c.metric = 'percentile' and c.span = '10' and c.percentile_window = '1y'
             then u.percentile_10w_1y
           when c.metric = 'percentile' and c.span = '20' and c.percentile_window = '1y'
             then u.percentile_20w_1y
           when c.metric = 'percentile' and c.span = '30' and c.percentile_window = '1y'
             then u.percentile_30w_1y
           when c.metric = 'percentile' and c.span = '40' and c.percentile_window = '1y'
             then u.percentile_40w_1y
           when c.metric = 'percentile' and c.span = '50' and c.percentile_window = '1y'
             then u.percentile_50w_1y
           when c.metric = 'percentile' and c.span = '5' and c.percentile_window = '2y'
             then u.percentile_5w_2y
           when c.metric = 'percentile' and c.span = '10' and c.percentile_window = '2y'
             then u.percentile_10w_2y
           when c.metric = 'percentile' and c.span = '20' and c.percentile_window = '2y'
             then u.percentile_20w_2y
           when c.metric = 'percentile' and c.span = '30' and c.percentile_window = '2y'
             then u.percentile_30w_2y
           when c.metric = 'percentile' and c.span = '40' and c.percentile_window = '2y'
             then u.percentile_40w_2y
           when c.metric = 'percentile' and c.span = '50' and c.percentile_window = '2y'
             then u.percentile_50w_2y
           when c.metric = 'connectChange' and c.span = '5w'
             then u.connect_change_5w_pct
           when c.metric = 'shortChange' and c.span = '5w'
             then u.short_change_5w_pct
         end as actual_value
  from universe u
  cross join conditions c
  left join lateral (
    select r.excess_return_pct
    from public.hk_market_insight_monthly_returns r
    where r.index_code = u.index_code
      and r.stock_code = u.stock_code
      and r.month_start = case
        when c.span = 'month'
          then date_trunc(
            'month', current_timestamp at time zone 'Asia/Hong_Kong'
          )::date
        when c.span = 'specific'
             and coalesce(c.month_text, '') ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
          then (c.month_text || '-01')::date
      end
    limit 1
  ) monthly on c.metric = 'excess' and c.span in ('month', 'specific')
),
summarized as (
  select e.index_code,
         e.stock_code,
         bool_and(
           case
             when e.actual_value is null or e.expected_value is null then false
             when e.comparison_operator = 'lt' then e.actual_value < e.expected_value
             when e.comparison_operator = 'eq' then abs(e.actual_value - e.expected_value) < 0.005
             when e.comparison_operator = 'gt' then e.actual_value > e.expected_value
             else false
           end
         ) as matches,
         count(*) filter (
           where e.actual_value is null
              or e.expected_value is null
              or e.comparison_operator is null
              or e.comparison_operator not in ('lt', 'eq', 'gt')
         )::integer as missing_condition_count
  from evaluated e
  group by e.index_code, e.stock_code
)
select s.index_code, s.stock_code, s.matches, s.missing_condition_count
from summarized s
order by s.index_code, s.stock_code;
$$;

revoke all on function public.filter_hk_market_insights(text[], jsonb) from public;
revoke all on function public.filter_hk_market_insights(text[], jsonb) from anon;
grant execute on function public.filter_hk_market_insights(text[], jsonb) to authenticated;
grant execute on function public.filter_hk_market_insights(text[], jsonb) to service_role;

alter table public.market_data_ingestion_runs
  drop constraint if exists market_data_ingestion_runs_dataset_check;
alter table public.market_data_ingestion_runs
  add constraint market_data_ingestion_runs_dataset_check
  check (dataset in (
    'hsci_constituents', 'short_positions', 'stock_connect', 'weekly_metrics',
    'monthly_metrics', 'hkex_share_capital'
  ));

commit;
