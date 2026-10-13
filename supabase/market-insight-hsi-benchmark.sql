-- Unified HSI benchmark for weekly/monthly excess returns.
-- Retains constituent groups, RLS, prices, and original component returns.
begin;
alter table public.market_index_weekly_prices drop constraint if exists market_index_weekly_prices_index_code_check;
alter table public.market_index_weekly_prices add constraint market_index_weekly_prices_index_code_check check (index_code in ('HSI','HSTECH','HSLI','HSMI','HSSI'));
alter table public.market_index_monthly_prices drop constraint if exists market_index_monthly_prices_index_code_check;
alter table public.market_index_monthly_prices add constraint market_index_monthly_prices_index_code_check check (index_code in ('HSI','HSTECH','HSLI','HSMI','HSSI'));
alter table public.hk_market_insight_metrics_weekly drop constraint if exists hk_market_insight_metrics_weekly_index_return_quality_check;
alter table public.hk_market_insight_metrics_weekly add constraint hk_market_insight_metrics_weekly_index_return_quality_check check (index_return_quality in ('official_index','constituent_equal_weight','official_hsi'));
alter table public.hk_market_insight_monthly_returns drop constraint if exists hk_market_insight_monthly_returns_index_return_quality_check;
alter table public.hk_market_insight_monthly_returns add constraint hk_market_insight_monthly_returns_index_return_quality_check check (index_return_quality in ('official_index','constituent_equal_weight','official_hsi'));
-- Do not serve old-benchmark excess values during or after a partial backfill.
-- Original stock/index returns remain available to reconstruct the old difference.
update public.hk_market_insight_metrics_weekly set excess_one_week_return_pct = null, excess_five_week_return_pct = null where index_return_quality <> 'official_hsi' and (excess_one_week_return_pct is not null or excess_five_week_return_pct is not null);
update public.hk_market_insight_monthly_returns set excess_return_pct = null where index_return_quality <> 'official_hsi' and excess_return_pct is not null;
commit;
