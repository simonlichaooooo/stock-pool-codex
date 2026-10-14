-- 将港股通作为独立市场洞察范围；可重复执行，便于失败后安全重跑回填。
begin;

alter table public.hk_market_insight_metrics_weekly
  drop constraint if exists hk_market_insight_metrics_weekly_index_code_check;
alter table public.hk_market_insight_metrics_weekly
  add constraint hk_market_insight_metrics_weekly_index_code_check
  check (index_code in ('HSTECH', 'HSLI', 'HSMI', 'HSSI', 'STOCK_CONNECT'));

alter table public.hk_market_insight_monthly_returns
  drop constraint if exists hk_market_insight_monthly_returns_index_code_check;
alter table public.hk_market_insight_monthly_returns
  add constraint hk_market_insight_monthly_returns_index_code_check
  check (index_code in ('HSTECH', 'HSLI', 'HSMI', 'HSSI', 'STOCK_CONNECT'));

alter table public.market_insight_ai_analyses
  drop constraint if exists market_insight_ai_analyses_index_code_check;
alter table public.market_insight_ai_analyses
  add constraint market_insight_ai_analyses_index_code_check
  check (index_code in ('HSTECH', 'HSLI', 'HSMI', 'HSSI', 'STOCK_CONNECT'));

commit;
