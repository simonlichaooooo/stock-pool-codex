-- 四个市场洞察指数的历史股本及持仓比例回填。
-- 请在 Supabase SQL Editor 中完整执行一次。

create table if not exists public.hk_issued_shares_monthly (
  stock_code text not null references public.market_securities(stock_code) on delete cascade,
  period_end date not null,
  issued_shares bigint not null check (issued_shares > 0),
  source_quality text not null check (source_quality in ('hkex_monthly_return', 'vendor_estimate')),
  source_url text not null,
  observations integer not null default 1 check (observations > 0),
  ingested_at timestamptz not null default now(),
  primary key (stock_code, period_end)
);

create index if not exists hk_issued_shares_monthly_lookup_idx
  on public.hk_issued_shares_monthly(stock_code, period_end desc);

alter table public.hk_issued_shares_monthly enable row level security;
grant select on public.hk_issued_shares_monthly to authenticated;
grant select, insert, update, delete on public.hk_issued_shares_monthly to service_role;

drop policy if exists "Authenticated users read issued shares history" on public.hk_issued_shares_monthly;
create policy "Authenticated users read issued shares history"
on public.hk_issued_shares_monthly for select to authenticated using (true);

create or replace function public.refresh_hk_holding_ratios()
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  short_updated integer := 0;
  connect_updated integer := 0;
begin
  with resolved as (
    select s.stock_code, s.report_date,
      (select h.issued_shares from public.hk_issued_shares_monthly h
       where h.stock_code = s.stock_code and h.period_end <= s.report_date
       order by h.period_end desc limit 1) as issued_shares
    from public.hk_short_positions_weekly s
  )
  update public.hk_short_positions_weekly s
  set issued_shares = resolved.issued_shares,
      short_ratio_pct = s.short_shares::numeric / resolved.issued_shares * 100,
      ratio_quality = 'licensed_vendor'
  from resolved
  where resolved.stock_code = s.stock_code and resolved.report_date = s.report_date
    and resolved.issued_shares is not null
    and (s.issued_shares is distinct from resolved.issued_shares or s.short_ratio_pct is null);
  get diagnostics short_updated = row_count;

  with resolved as (
    select h.stock_code, h.holding_date,
      (select s.issued_shares from public.hk_issued_shares_monthly s
       where s.stock_code = h.stock_code and s.period_end <= h.holding_date
       order by s.period_end desc limit 1) as issued_shares
    from public.hk_stock_connect_holdings_daily h
    where h.total_holding_shares is not null
  )
  update public.hk_stock_connect_holdings_daily h
  set issued_shares = resolved.issued_shares,
      holding_ratio_pct = h.total_holding_shares::numeric / resolved.issued_shares * 100,
      ratio_quality = 'licensed_vendor'
  from resolved
  where resolved.stock_code = h.stock_code and resolved.holding_date = h.holding_date
    and resolved.issued_shares is not null
    and (h.issued_shares is distinct from resolved.issued_shares or h.holding_ratio_pct is null);
  get diagnostics connect_updated = row_count;

  return jsonb_build_object('short_updated', short_updated, 'connect_updated', connect_updated);
end;
$$;

revoke all on function public.refresh_hk_holding_ratios() from public, anon, authenticated;
grant execute on function public.refresh_hk_holding_ratios() to service_role;
