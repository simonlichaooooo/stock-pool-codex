-- Existing grants and SECURITY INVOKER are preserved. No data or policy changes.
begin;
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
set jit = off
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
-- Compute holdings once per stock, before expanding the condition list.
universe as materialized (
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


commit;
