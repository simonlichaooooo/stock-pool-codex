-- 港交所披露易官方股本历史。
-- 请在 Supabase SQL Editor 中完整执行一次；可重复执行。

create table if not exists public.hkex_share_capital_filings (
  document_id text primary key,
  stock_code text not null references public.market_securities(stock_code) on delete cascade,
  filing_type text not null check (filing_type in ('monthly_return', 'next_day_disclosure')),
  release_at timestamptz not null,
  title text not null,
  source_url text not null,
  parse_status text not null check (parse_status in ('parsed', 'failed', 'no_listed_class')),
  parser_version text not null,
  parse_error text,
  parsed_at timestamptz not null default now()
);

create index if not exists hkex_share_capital_filings_stock_date_idx
  on public.hkex_share_capital_filings(stock_code, release_at desc);
create index if not exists hkex_share_capital_filings_status_idx
  on public.hkex_share_capital_filings(parse_status, release_at desc);

create table if not exists public.hk_issued_shares_official (
  stock_code text not null references public.market_securities(stock_code) on delete cascade,
  effective_date date not null,
  share_class text not null default 'listed shares',
  issued_shares bigint not null check (issued_shares > 0),
  treasury_shares bigint not null default 0 check (treasury_shares >= 0),
  issued_shares_ex_treasury bigint not null check (issued_shares_ex_treasury > 0),
  source_type text not null check (source_type in ('hkex_monthly_return', 'hkex_next_day_disclosure')),
  source_priority smallint not null check (source_priority in (80, 100)),
  source_url text not null,
  document_id text not null references public.hkex_share_capital_filings(document_id) on delete cascade,
  release_at timestamptz not null,
  parser_version text not null,
  ingested_at timestamptz not null default now(),
  primary key (stock_code, effective_date, share_class),
  check (issued_shares = issued_shares_ex_treasury + treasury_shares),
  check (
    (source_type = 'hkex_monthly_return' and source_priority = 80)
    or (source_type = 'hkex_next_day_disclosure' and source_priority = 100)
  )
);

create index if not exists hk_issued_shares_official_lookup_idx
  on public.hk_issued_shares_official(stock_code, effective_date desc, source_priority desc);

create or replace function public.preserve_higher_priority_hkex_share_capital()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if old.source_priority > new.source_priority then
    return old;
  end if;
  new.ingested_at := now();
  return new;
end;
$$;

drop trigger if exists preserve_higher_priority_hkex_share_capital
  on public.hk_issued_shares_official;
create trigger preserve_higher_priority_hkex_share_capital
before update on public.hk_issued_shares_official
for each row execute function public.preserve_higher_priority_hkex_share_capital();

alter table public.hkex_share_capital_filings enable row level security;
alter table public.hk_issued_shares_official enable row level security;

grant select on public.hkex_share_capital_filings to authenticated;
grant select on public.hk_issued_shares_official to authenticated;
grant select, insert, update, delete on public.hkex_share_capital_filings to service_role;
grant select, insert, update, delete on public.hk_issued_shares_official to service_role;

drop policy if exists "Authenticated users read HKEX share-capital filings"
  on public.hkex_share_capital_filings;
create policy "Authenticated users read HKEX share-capital filings"
on public.hkex_share_capital_filings for select to authenticated using (true);

drop policy if exists "Authenticated users read official issued shares"
  on public.hk_issued_shares_official;
create policy "Authenticated users read official issued shares"
on public.hk_issued_shares_official for select to authenticated using (true);

alter table public.market_data_ingestion_runs
  drop constraint if exists market_data_ingestion_runs_dataset_check;
alter table public.market_data_ingestion_runs
  add constraint market_data_ingestion_runs_dataset_check
  check (dataset in (
    'hsci_constituents', 'short_positions', 'stock_connect', 'weekly_metrics',
    'hkex_share_capital'
  ));

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
      coalesce(official.issued_shares, fallback.issued_shares) as issued_shares,
      case when official.issued_shares is not null then 'official' else 'licensed_vendor' end as quality
    from public.hk_short_positions_weekly s
    left join lateral (
      select h.issued_shares_ex_treasury as issued_shares
      from public.hk_issued_shares_official h
      where h.stock_code = s.stock_code and h.effective_date <= s.report_date
      order by h.effective_date desc, h.source_priority desc
      limit 1
    ) official on true
    left join lateral (
      select h.issued_shares
      from public.hk_issued_shares_monthly h
      where h.stock_code = s.stock_code and h.period_end <= s.report_date
      order by h.period_end desc
      limit 1
    ) fallback on official.issued_shares is null
  )
  update public.hk_short_positions_weekly s
  set issued_shares = resolved.issued_shares,
      short_ratio_pct = s.short_shares::numeric / resolved.issued_shares * 100,
      ratio_quality = resolved.quality
  from resolved
  where resolved.stock_code = s.stock_code and resolved.report_date = s.report_date
    and resolved.issued_shares is not null
    and (
      s.issued_shares is distinct from resolved.issued_shares
      or s.short_ratio_pct is null
      or s.ratio_quality is distinct from resolved.quality
    );
  get diagnostics short_updated = row_count;

  with resolved as (
    select h.stock_code, h.holding_date,
      coalesce(official.issued_shares, fallback.issued_shares) as issued_shares,
      case when official.issued_shares is not null then 'official' else 'licensed_vendor' end as quality
    from public.hk_stock_connect_holdings_daily h
    left join lateral (
      select s.issued_shares_ex_treasury as issued_shares
      from public.hk_issued_shares_official s
      where s.stock_code = h.stock_code and s.effective_date <= h.holding_date
      order by s.effective_date desc, s.source_priority desc
      limit 1
    ) official on true
    left join lateral (
      select s.issued_shares
      from public.hk_issued_shares_monthly s
      where s.stock_code = h.stock_code and s.period_end <= h.holding_date
      order by s.period_end desc
      limit 1
    ) fallback on official.issued_shares is null
    where h.total_holding_shares is not null
  )
  update public.hk_stock_connect_holdings_daily h
  set issued_shares = resolved.issued_shares,
      holding_ratio_pct = h.total_holding_shares::numeric / resolved.issued_shares * 100,
      ratio_quality = resolved.quality
  from resolved
  where resolved.stock_code = h.stock_code and resolved.holding_date = h.holding_date
    and resolved.issued_shares is not null
    and (
      h.issued_shares is distinct from resolved.issued_shares
      or h.holding_ratio_pct is null
      or h.ratio_quality is distinct from resolved.quality
    );
  get diagnostics connect_updated = row_count;

  return jsonb_build_object('short_updated', short_updated, 'connect_updated', connect_updated);
end;
$$;

revoke all on function public.refresh_hk_holding_ratios() from public, anon, authenticated;
grant execute on function public.refresh_hk_holding_ratios() to service_role;

create or replace view public.hk_official_share_capital_coverage
with (security_invoker = true)
as
with universe as (
  select distinct index_code, stock_code
  from public.hk_market_insight_metrics_weekly
  where index_code in ('HSTECH', 'HSLI', 'HSMI', 'HSSI')
), coverage as (
  select stock_code,
         min(effective_date) as first_official_date,
         max(effective_date) as latest_official_date,
         count(*) as official_event_count
  from public.hk_issued_shares_official
  group by stock_code
)
select u.index_code, count(*) as stock_count,
       count(c.stock_code) as stocks_with_official_data,
       count(*) - count(c.stock_code) as stocks_missing_official_data,
       min(c.first_official_date) as first_official_date,
       max(c.latest_official_date) as latest_official_date,
       coalesce(sum(c.official_event_count), 0) as official_event_count
from universe u
left join coverage c on c.stock_code = u.stock_code
group by u.index_code
order by u.index_code;

grant select on public.hk_official_share_capital_coverage to authenticated;
