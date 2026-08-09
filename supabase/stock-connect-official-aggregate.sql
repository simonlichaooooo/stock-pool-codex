-- 港交所官方沪深港股通合计持仓。请在 Supabase SQL Editor 完整执行一次；可重复执行。

alter table public.hk_stock_connect_holdings_daily
  add column if not exists aggregate_source_url text,
  add column if not exists source_reported_ratio_pct numeric(14, 8);

do $$
declare item record;
begin
  for item in
    select conname from pg_constraint
    where conrelid = 'public.hk_stock_connect_holdings_daily'::regclass and contype = 'c'
  loop
    execute format('alter table public.hk_stock_connect_holdings_daily drop constraint %I', item.conname);
  end loop;
end $$;

alter table public.hk_stock_connect_holdings_daily
  add constraint hk_stock_connect_sh_nonnegative check (sh_holding_shares is null or sh_holding_shares >= 0),
  add constraint hk_stock_connect_sz_nonnegative check (sz_holding_shares is null or sz_holding_shares >= 0),
  add constraint hk_stock_connect_total_nonnegative check (total_holding_shares is null or total_holding_shares >= 0),
  add constraint hk_stock_connect_issued_positive check (issued_shares is null or issued_shares > 0),
  add constraint hk_stock_connect_ratio_nonnegative check (holding_ratio_pct is null or holding_ratio_pct >= 0),
  add constraint hk_stock_connect_source_ratio_nonnegative check (source_reported_ratio_pct is null or source_reported_ratio_pct >= 0),
  add constraint hk_stock_connect_ratio_quality_allowed
    check (ratio_quality in ('official', 'licensed_vendor', 'missing_denominator')),
  add constraint hk_stock_connect_completeness_allowed
    check (completeness in ('complete', 'partial_sh', 'partial_sz', 'official_aggregate')),
  add constraint hk_stock_connect_completeness_shape check (
    (completeness = 'complete' and sh_holding_shares is not null and sz_holding_shares is not null
      and total_holding_shares = sh_holding_shares + sz_holding_shares)
    or (completeness = 'partial_sh' and sh_holding_shares is not null and sz_holding_shares is null and total_holding_shares is null)
    or (completeness = 'partial_sz' and sh_holding_shares is null and sz_holding_shares is not null and total_holding_shares is null)
    or (completeness = 'official_aggregate' and sh_holding_shares is null and sz_holding_shares is null
      and total_holding_shares is not null and aggregate_source_url is not null)
  ),
  add constraint hk_stock_connect_ratio_shape check (
    (issued_shares is null and holding_ratio_pct is null and ratio_quality = 'missing_denominator')
    or (issued_shares is not null and holding_ratio_pct is not null and ratio_quality <> 'missing_denominator')
  );

create index if not exists hk_stock_connect_complete_lookup_idx
  on public.hk_stock_connect_holdings_daily(stock_code, holding_date desc)
  where total_holding_shares is not null;
